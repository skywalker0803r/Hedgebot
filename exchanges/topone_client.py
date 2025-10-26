import time
import hashlib
import requests
import logging
import json 

class TopOneClient:
    def __init__(self, api_key: str, secret_key: str, memo: str = None):
        self.api_key = api_key
        self.secret_key = secret_key
        self.memo = memo
        self.base_url = "https://openapi.top.one"
        self.logger = logging.getLogger(__name__)

    def _get_signed_headers(self, method, path):
        timestamp = str(int(time.time() * 1000))
        
        signature_payload = f"Method={method.upper()}&Path={path}&Timestamp={timestamp}&Secret={self.secret_key}"

        signature = hashlib.sha256(signature_payload.encode('utf-8')).hexdigest()

        return {
            "X-Time": timestamp,
            "X-Openapi-Key": self.api_key,
            "X-Openapi-Sign": signature,
            "Content-Type": "application/json"
        }

    def get_balance(self):
        path = "/api/v1/balance"
        method = "GET"
        
        headers = self._get_signed_headers(method, path)

        try:
            response = requests.get(self.base_url + path, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get("status") and data.get("status").get("error") is None:
                trading_account = data.get("data", {}).get("trading", [])
                usdt_asset = next((asset for asset in trading_account if asset.get('code') == 'USDT'), None)
                if usdt_asset and 'available' in usdt_asset:
                    return float(usdt_asset['available'])
                else:
                    self.logger.info("USDT asset not found in trading account.")
                    return 0.0
            else:
                message = data.get("status", {}).get("messages", "Unknown error")
                self.logger.error(f"API error: {message}")
                return None

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request failed: {e}")
            return None
        except ValueError: # Catches JSON decoding errors
            self.logger.error("Failed to decode JSON response.")
            return None

    def place_order(self, symbol: str, side: str, margin: float, leverage: int, tp_price: float, sl_price: float):
        path = "/fapi/v1/create-order"
        method = "POST"

        headers = self._get_signed_headers(method, path)

        if side.lower() == 'long':
            api_side = "buy"
            api_position_side = "long"
        elif side.lower() == 'short':
            api_side = "sell"
            api_position_side = "short"
        else:
            self.logger.error(f"Invalid side: {side}. Must be 'long' or 'short'.")
            return None

        payload = {
            "pair": symbol,
            "side": api_side,
            "position_side": api_position_side,
            "leverage": leverage,
            "margin_mode": 1, #逐倉
            "margin": str(margin),
            "take_profit_price": str(tp_price),
            "stop_loss_price": str(sl_price),
        }

        try:
            response = requests.post(self.base_url + path, headers=headers, data=json.dumps(payload))
            response.raise_for_status()
            data = response.json()

            if data.get("status") and data.get("status").get("error") is None:
                return data
            else:
                message = data.get("status", {}).get("messages", "Unknown error")
                self.logger.error(f"API error: {message}")
                return None

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request failed: {e}")
            return None
        except ValueError: 
            self.logger.error("Failed to decode JSON response.")
            return None

    def get_open_positions(self, symbol: str = None):
        path = "/fapi/v1/position"
        method = "GET"
        
        headers = self._get_signed_headers(method, path)
        params = {"status": 1} # Filter for open positions

        if symbol:
            params["pair"] = symbol

        try:
            response = requests.get(self.base_url + path, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

            if data.get("status") and data.get("status").get("error") is None:
                return data.get("data", {}).get("list", [])
            else:
                message = data.get("status", {}).get("messages", "Unknown error")
                self.logger.error(f"API error getting open positions: {message}")
                return None
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request failed getting open positions: {e}")
            return None
        except ValueError:
            self.logger.error("Failed to decode JSON response getting open positions.")
            return None

    def get_position(self, symbol: str):
        """Get position for specific symbol (compatible with BitmartClient.get_position)"""
        try:
            positions = self.get_open_positions(symbol)
            if positions and len(positions) > 0:
                position = positions[0]
                self.logger.info(f"Raw position data from get_open_positions for {symbol}: {position}")
                return {
                    'symbol': position.get('pair', symbol),
                    'size': position.get('quantity', '0'),
                    'side': position.get('side', None),  # TopOne uses 'side' field
                    'position_id': position.get('position_id'),
                    'entry_price': position.get('open_price', '0'),
                    'unrealized_pnl': position.get('unrealized_pnl', '0')
                }
            else:
                self.logger.info(f"No open position found for {symbol}.")
                return None
        except Exception as e:
            self.logger.error(f"Failed to get position for {symbol}: {e}")
            return None

    def close_position(self, symbol: str):
        open_positions = self.get_open_positions(symbol)
        if not open_positions:
            self.logger.info(f"No open positions found for {symbol}.")
            return None

        results = []
        for position in open_positions:
            position_id = position['position_id']
            quantity = position['quantity'] 

            path = "/fapi/v1/close"
            method = "POST"
            headers = self._get_signed_headers(method, path)
            payload = {
                "position_id": position_id,
                "quantity": quantity 
            }

            try:
                response = requests.post(self.base_url + path, headers=headers, data=json.dumps(payload))
                response.raise_for_status()
                data = response.json()

                if data.get("status") and data.get("status").get("error") is None:
                    self.logger.info(f"Position {position_id} closed successfully: {data}")
                    results.append({"position_id": position_id, "status": "success", "response": data})
                else:
                    message = data.get("status", {}).get("messages", "Unknown error")
                    self.logger.error(f"API error closing position {position_id}: {message}")
                    results.append({"position_id": position_id, "status": "failed", "message": message})
            except requests.exceptions.RequestException as e:
                self.logger.error(f"Request failed closing position {position_id}: {e}")
                results.append({"position_id": position_id, "status": "failed", "message": str(e)})
            except ValueError:
                self.logger.error(f"Failed to decode JSON response closing position {position_id}.")
                results.append({"position_id": position_id, "status": "failed", "message": "Invalid JSON response"})
        
        return results