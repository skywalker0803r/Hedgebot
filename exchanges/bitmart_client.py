import logging
from bitmart.api_contract import APIContract
from bitmart.lib.cloud_exceptions import APIException
from bitmart.lib.cloud_utils import config_logging

class BitmartClient:
    def __init__(self, api_key: str, secret_key: str, memo: str):
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

    def get_kline_data(self, symbol: str, step: int, start_time: int, end_time: int):
        try:
            kline_response = self.futuresAPI.get_kline(symbol, step, start_time, end_time)
            # kline_response is a tuple, first element is the data
            # data is {'code': 1000, 'message': 'Ok', 'data': [...], 'trace': '...'}
            # The actual kline data is in data['data']
            return kline_response[0]['data']
        except (APIException, IndexError, KeyError) as e:
            self.logger.error(f"Failed to get kline data for {symbol}: {e}")
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
                open_type="isolated" #逐倉
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

    def get_position(self, symbol: str):
        try:
            position_response = self.futuresAPI.get_position(symbol)
            positions = position_response[0]['data']
            for position in positions:
                if position['symbol'] == symbol:
                    return position
            self.logger.info(f"No open position found for {symbol}.")
            return None
        except (APIException, IndexError, KeyError) as e:
            self.logger.error(f"Failed to get position: {e}")
            return None

    def close_position(self, symbol: str):
        position = self.get_position(symbol)
        if not position:
            self.logger.info(f"No open position found for {symbol}.")
            return None

        position_type = position['position_type']
        current_amount = int(position['current_amount'])

        if current_amount == 0:
            self.logger.info(f"Position for {symbol} has size 0, nothing to close.")
            return None

        close_side = 0
        if position_type == 1: # Long position
            close_side = 3 # sell_close_long
        elif position_type == 2: # Short position (assuming it's 2, based on buy_close_short)
            close_side = 2 # buy_close_short
        else:
            self.logger.error(f"Unknown position type: {position_type}")
            return None

        try:
            leverage = position['leverage']
            open_type = position['margin_type'].lower()

            response = self.futuresAPI.post_submit_order(
                contract_symbol=symbol,
                type="market",
                side=close_side,
                size=current_amount,
                leverage=leverage,
                open_type=open_type
            )
            return response
        except (APIException, KeyError) as error:
            self.logger.error(f"Failed to close position: {error}")
            return None
