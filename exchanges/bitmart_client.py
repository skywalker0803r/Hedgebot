import logging
from bitmart.api_contract import APIContract
from bitmart.lib.cloud_exceptions import APIException
from bitmart.lib.cloud_utils import config_logging

class BitmartClient:
    def __init__(self, api_key: str, secret_key: str, memo: str):
        config_logging(logging, logging.INFO)
        self.logger = logging.getLogger(__name__)
        self.futuresAPI = APIContract(api_key=api_key,
                                      secret_key=secret_key,
                                      memo=memo,
                                      logger=self.logger)

    def get_balance(self):
        try:
            response = self.futuresAPI.get_assets_detail()[0]
            usdt_asset = next((asset for asset in response['data'] if asset['currency'] == 'USDT'), None)
            if usdt_asset:
                return float(usdt_asset['available_balance'])
            else:
                self.logger.info("USDT asset not found")
                return None
        except APIException as error:
            self.logger.error(f"Found error. status: {error.status_code}, error message: {error.response}")
            return None

    def get_current_price(self, symbol: str):
        try:
            depth_data = self.futuresAPI.get_depth(symbol)[0]['data']
            if depth_data and depth_data.get('bids') and depth_data.get('asks'):
                best_bid = float(depth_data['bids'][0][0])
                best_ask = float(depth_data['asks'][0][0])
                return (best_bid + best_ask) / 2
            else:
                self.logger.error(f"Could not get bids/asks from depth data.")
                return None
        except (APIException, IndexError, KeyError) as error:
            self.logger.error(f"Failed to get depth: {error}")
            return None

    def get_trade_fee(self, symbol: str):
        try:
            fee_response = self.futuresAPI.get_trade_fee_rate(symbol)
            return fee_response[0]['data']
        except (APIException, IndexError, KeyError) as e:
            self.logger.error(f"Failed to get trade fee: {e}")
            return None

    def place_order(self, symbol: str, side: str, margin: float, leverage: int, tp_price: float, sl_price: float):
        # 1. Get current price
        current_price = self.get_current_price(symbol)
        if not current_price:
            return None

        # 2. Get contract details
        try:
            details_data = self.futuresAPI.get_details(symbol)[0]['data']
            symbol_details = details_data['symbols'][0]
            contract_size = float(symbol_details['contract_size'])
            
            precision_str = symbol_details['price_precision']
            if '.' in precision_str:
                price_precision = len(precision_str.split('.')[1])
            else:
                price_precision = 0

        except (APIException, IndexError, KeyError, ValueError) as e:
            self.logger.error(f"Could not get contract details: {e}")
            return None
            
        # 3. Calculate size and round TP/SL
        size = int((margin * leverage) / (current_price * contract_size))
        
        rounded_tp_price = round(tp_price, price_precision)
        rounded_sl_price = round(sl_price, price_precision)

        # 4. Set leverage
        try:
            self.futuresAPI.post_submit_leverage(
                contract_symbol=symbol,
                leverage=str(leverage),
                open_type="isolated"
            )
        except APIException as error:
            self.logger.error(f"Failed to set leverage: {error}")
            # It might be already set, so we can try to continue

        # 5. Place order
        order_side_map = {'long': 1, 'short': 4} # 1: buy_open_long, 4: sell_open_short
        order_side = order_side_map.get(side.lower())
        if not order_side:
            self.logger.error(f"Invalid side: {side}. Must be 'long' or 'short'.")
            return None

        try:
            response = self.futuresAPI.post_submit_order(
                contract_symbol=symbol,
                type="market",
                side=order_side,
                leverage=str(leverage),
                open_type="isolated",
                size=size,
                preset_take_profit_price=str(rounded_tp_price),
                preset_stop_loss_price=str(rounded_sl_price)
            )
            return response
        except APIException as error:
            self.logger.error(f"Failed to place order: {error}")
            return None
