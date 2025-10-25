import pandas as pd
import ta
from datetime import datetime, timedelta
import time
import logging

from exchanges.bitmart_client import BitmartClient
from exchanges.topone_client import TopOneClient

logger = logging.getLogger(__name__)

def run_rsi_strategy(bitmart_client: BitmartClient, topone_client: TopOneClient, **kwargs):
    logger.info("Running RSI Strategy...")

    symbol = kwargs.get('symbol')
    margin = kwargs.get('margin')
    leverage = kwargs.get('leverage')
    tp_percentage = kwargs.get('tp_percentage')
    sl_percentage = kwargs.get('sl_percentage')

    results = {
        "strategy": "RSI",
        "status": "failed",
        "message": "",
        "bitmart_order": None,
        "topone_order": None,
        "bitmart_close": None,
        "topone_close": None,
    }

    # --- Configuration for RSI ---
    RSI_PERIOD = 14
    RSI_OVERBOUGHT = 80
    RSI_OVERSOLD = 20
    KLINE_INTERVAL = 1 # 1 minute klines
    KLINE_LIMIT = 100 # Fetch last 100 klines (need enough for RSI_PERIOD)

    # --- Fetch K-line data from Bitmart ---
    logger.info(f"Fetching {KLINE_LIMIT} {KLINE_INTERVAL}-minute K-lines for {symbol} from Bitmart...")
    end_time = int(time.time())
    start_time = int(end_time - (KLINE_LIMIT * KLINE_INTERVAL * 60)) # KLINE_LIMIT minutes ago

    kline_data = bitmart_client.get_kline_data(symbol, KLINE_INTERVAL, start_time, end_time)

    if not kline_data:
        logger.error("Failed to fetch K-line data or K-line data is empty. Cannot run RSI strategy.")
        results["message"] = "Failed to fetch K-line data."
        return results

    # --- Process K-line data ---
    df = pd.DataFrame(kline_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['close'] = pd.to_numeric(df['close'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

    # --- Calculate RSI ---
    logger.info("Calculating RSI indicator...")
    df['rsi'] = ta.momentum.rsi(df['close'], window=RSI_PERIOD, fillna=False)

    # Ensure we have enough data for RSI calculation
    if len(df) < RSI_PERIOD:
        logger.warning("Not enough K-line data to calculate RSI. Please increase KLINE_LIMIT.")
        results["message"] = "Not enough K-line data for RSI."
        return results

    last_rsi = df['rsi'].iloc[-1]
    logger.info(f"Last RSI: {last_rsi:.2f}")

    # --- Determine trading signal ---
    signal = None
    if last_rsi < RSI_OVERSOLD:
        signal = "oversold" # Buy signal
        logger.info(f"RSI ({last_rsi:.2f}) is below {RSI_OVERSOLD}! Opening long position.")
    elif last_rsi > RSI_OVERBOUGHT:
        signal = "overbought" # Sell signal
        logger.warning(f"RSI ({last_rsi:.2f}) is above {RSI_OVERBOUGHT}! Closing position.")
    else:
        logger.info("RSI is within normal range. No action taken.")
        results["status"] = "no_signal"
        results["message"] = "RSI is within normal range."
        return results

    # --- Execute trades based on signal ---
    current_price = df['close'].iloc[-1] # Use the latest close price as current price
    logger.info(f"Current price for order execution: {current_price}")

    if signal == "oversold":
        # Open long on Bitmart, short on TopOne
        bitmart_side = "long"
        topone_side = "short"
        
        bitmart_tp_price = current_price * (1 + tp_percentage / 100)
        bitmart_sl_price = current_price * (1 - sl_percentage / 100)
        topone_tp_price = current_price * (1 - tp_percentage / 100)
        topone_sl_price = current_price * (1 + sl_percentage / 100)

        logger.info("Opening Positions...")
        bitmart_order_response = bitmart_client.place_order(
            symbol=symbol, side=bitmart_side, margin=margin, leverage=leverage,
            tp_price=bitmart_tp_price, sl_price=bitmart_sl_price
        )
        if bitmart_order_response:
            logger.info(f"Bitmart order placed successfully: {bitmart_order_response}")
            results["bitmart_order"] = bitmart_order_response
        else:
            logger.error("Failed to place Bitmart order.")
            results["message"] = "Failed to place Bitmart order."

        topone_order_response = topone_client.place_order(
            symbol=symbol, side=topone_side, margin=margin, leverage=leverage,
            tp_price=topone_tp_price, sl_price=topone_sl_price
        )
        if topone_order_response:
            logger.info(f"TopOne order placed successfully: {topone_order_response}")
            results["topone_order"] = topone_order_response
        else:
            logger.error("Failed to place TopOne order.")
            results["message"] += " Failed to place TopOne order."

    elif signal == "overbought":
        # Close existing positions on both exchanges
        logger.info("Closing Positions...")
        bitmart_close_response = bitmart_client.close_position(symbol)
        if bitmart_close_response:
            logger.info(f"Bitmart position closed successfully: {bitmart_close_response}")
            results["bitmart_close"] = bitmart_close_response
        else:
            logger.error("Failed to close Bitmart position.")
            results["message"] = "Failed to close Bitmart position."

        topone_close_response = topone_client.close_position(symbol)
        if topone_close_response:
            logger.info(f"TopOne position closed successfully: {topone_close_response}")
            results["topone_close"] = topone_close_response
        else:
            logger.error("Failed to close TopOne position.")
            results["message"] += " Failed to close TopOne position."

    results["status"] = "completed"
    results["message"] = "RSI strategy execution completed."
    logger.info("RSI Strategy Execution Completed!")
    return results
