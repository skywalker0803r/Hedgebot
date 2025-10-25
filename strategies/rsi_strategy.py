import streamlit as st
import pandas as pd
import ta 
from datetime import datetime, timedelta
import time 

from exchanges.bitmart_client import BitmartClient
from exchanges.topone_client import TopOneClient

def run_rsi_strategy(bitmart_client: BitmartClient, topone_client: TopOneClient, **kwargs):
    st.subheader("Running RSI Strategy...")

    symbol = kwargs.get('symbol')
    margin = kwargs.get('margin')
    leverage = kwargs.get('leverage')
    tp_percentage = kwargs.get('tp_percentage')
    sl_percentage = kwargs.get('sl_percentage')

    # --- Configuration for RSI ---
    RSI_PERIOD = 14
    RSI_OVERBOUGHT = 80
    RSI_OVERSOLD = 20
    KLINE_INTERVAL = 1 # 1 minute klines
    KLINE_LIMIT = 100 # Fetch last 100 klines (need enough for RSI_PERIOD)

    # --- Fetch K-line data from Bitmart ---
    st.info(f"Fetching {KLINE_LIMIT} {KLINE_INTERVAL}-minute K-lines for {symbol} from Bitmart...")
    end_time = int(time.time())
    start_time = int(end_time - (KLINE_LIMIT * KLINE_INTERVAL * 60)) # KLINE_LIMIT minutes ago

    kline_data = bitmart_client.get_kline_data(symbol, KLINE_INTERVAL, start_time, end_time)

    if not kline_data or not kline_data.get('klines'):
        st.error("Failed to fetch K-line data or K-line data is empty. Cannot run RSI strategy.")
        return

    # --- Process K-line data ---
    # K-line format: [timestamp, open, high, low, close, volume]
    df = pd.DataFrame(kline_data['klines'], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['close'] = pd.to_numeric(df['close'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms') # Bitmart kline timestamp is in ms

    # --- Calculate RSI ---
    st.info("Calculating RSI indicator...")
    df['rsi'] = ta.momentum.rsi(df['close'], window=RSI_PERIOD, fillna=False)

    # Ensure we have enough data for RSI calculation
    if len(df) < RSI_PERIOD:
        st.warning("Not enough K-line data to calculate RSI. Please increase KLINE_LIMIT.")
        return

    last_rsi = df['rsi'].iloc[-1]
    st.write(f"Last RSI: {last_rsi:.2f}")

    # --- Determine trading signal ---
    signal = None
    if last_rsi < RSI_OVERSOLD:
        signal = "oversold" # Buy signal
        st.success(f"RSI ({last_rsi:.2f}) is below {RSI_OVERSOLD}! Opening long position.")
    elif last_rsi > RSI_OVERBOUGHT:
        signal = "overbought" # Sell signal
        st.warning(f"RSI ({last_rsi:.2f}) is above {RSI_OVERBOUGHT}! Closing position.")
    else:
        st.info("RSI is within normal range. No action taken.")
        return

    # --- Execute trades based on signal ---
    current_price = df['close'].iloc[-1] # Use the latest close price as current price
    st.write(f"Current price for order execution: {current_price}")

    if signal == "oversold":
        # Open long on Bitmart, short on TopOne
        bitmart_side = "long"
        topone_side = "short"
        
        bitmart_tp_price = current_price * (1 + tp_percentage / 100)
        bitmart_sl_price = current_price * (1 - sl_percentage / 100)
        topone_tp_price = current_price * (1 - tp_percentage / 100)
        topone_sl_price = current_price * (1 + sl_percentage / 100)

        st.subheader("Opening Positions...")
        bitmart_order_response = bitmart_client.place_order(
            symbol=symbol, side=bitmart_side, margin=margin, leverage=leverage,
            tp_price=bitmart_tp_price, sl_price=bitmart_sl_price
        )
        if bitmart_order_response:
            st.success(f"Bitmart order placed successfully: {bitmart_order_response}")
        else:
            st.error("Failed to place Bitmart order.")

        topone_order_response = topone_client.place_order(
            symbol=symbol, side=topone_side, margin=margin, leverage=leverage,
            tp_price=topone_tp_price, sl_price=topone_sl_price
        )
        if topone_order_response:
            st.success(f"TopOne order placed successfully: {topone_order_response}")
        else:
            st.error("Failed to place TopOne order.")

    elif signal == "overbought":
        # Close existing positions on both exchanges
        st.subheader("Closing Positions...")
        bitmart_close_response = bitmart_client.close_position(symbol)
        if bitmart_close_response:
            st.success(f"Bitmart position closed successfully: {bitmart_close_response}")
        else:
            st.error("Failed to close Bitmart position.")

        topone_close_response = topone_client.close_position(symbol)
        if topone_close_response:
            st.success(f"TopOne position closed successfully: {topone_close_response}")
        else:
            st.error("Failed to close TopOne position.")

    st.subheader("RSI Strategy Execution Completed!")