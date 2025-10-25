import streamlit as st
import pandas as pd
import ta 
from datetime import datetime, timedelta
import time 

from exchanges.bitmart_client import BitmartClient
from exchanges.topone_client import TopOneClient

def run_macd_strategy(bitmart_client: BitmartClient, topone_client: TopOneClient, **kwargs):
    st.subheader("Running MACD Strategy...")

    symbol = kwargs.get('symbol')
    margin = kwargs.get('margin')
    leverage = kwargs.get('leverage')
    tp_percentage = kwargs.get('tp_percentage')
    sl_percentage = kwargs.get('sl_percentage')

    # --- Configuration for MACD ---
    FAST_PERIOD = 12
    SLOW_PERIOD = 26
    SIGNAL_PERIOD = 9
    KLINE_INTERVAL = 1 # 1 minute klines
    KLINE_LIMIT = 100 # Fetch last 100 klines

    # --- Fetch K-line data from Bitmart ---
    st.info(f"Fetching {KLINE_LIMIT} {KLINE_INTERVAL}-minute K-lines for {symbol} from Bitmart...")
    end_time = int(time.time())
    start_time = int(end_time - (KLINE_LIMIT * KLINE_INTERVAL * 60)) # KLINE_LIMIT minutes ago

    kline_data = bitmart_client.get_kline_data(symbol, KLINE_INTERVAL, start_time, end_time)

    if not kline_data or not kline_data.get('klines'):
        st.error("Failed to fetch K-line data or K-line data is empty. Cannot run MACD strategy.")
        return

    # --- Process K-line data ---
    # K-line format: [timestamp, open, high, low, close, volume]
    df = pd.DataFrame(kline_data['klines'], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['close'] = pd.to_numeric(df['close'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms') # Bitmart kline timestamp is in ms

    # --- Calculate MACD ---
    st.info("Calculating MACD indicator...")
    df['macd'] = ta.trend.macd(df['close'], window_slow=SLOW_PERIOD, window_fast=FAST_PERIOD, fillna=False)
    df['macd_signal'] = ta.trend.macd_signal(df['close'], window_slow=SLOW_PERIOD, window_fast=FAST_PERIOD, window_sign=SIGNAL_PERIOD, fillna=False)
    df['macd_diff'] = ta.trend.macd_diff(df['close'], window_slow=SLOW_PERIOD, window_fast=FAST_PERIOD, window_sign=SIGNAL_PERIOD, fillna=False)

    # Ensure we have enough data for MACD calculation
    if len(df) < SLOW_PERIOD + SIGNAL_PERIOD:
        st.warning("Not enough K-line data to calculate MACD. Please increase KLINE_LIMIT.")
        return

    # Get the last two MACD and Signal values to detect crosses
    last_macd = df['macd'].iloc[-1]
    last_signal = df['macd_signal'].iloc[-1]
    prev_macd = df['macd'].iloc[-2]
    prev_signal = df['macd_signal'].iloc[-2]

    st.write(f"Last MACD: {last_macd:.4f}, Last Signal: {last_signal:.4f}")
    st.write(f"Previous MACD: {prev_macd:.4f}, Previous Signal: {prev_signal:.4f}")

    # --- Determine trading signal ---
    signal = None
    if prev_macd < prev_signal and last_macd > last_signal:
        signal = "golden_cross" # Buy signal
        st.success("MACD Golden Cross detected! Opening long position.")
    elif prev_macd > prev_signal and last_macd < last_signal:
        signal = "death_cross" # Sell signal
        st.warning("MACD Death Cross detected! Closing position.")
    else:
        st.info("No MACD cross detected. No action taken.")
        return

    # --- Execute trades based on signal ---
    current_price = df['close'].iloc[-1] # Use the latest close price as current price
    st.write(f"Current price for order execution: {current_price}")

    if signal == "golden_cross":
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

    elif signal == "death_cross":
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

    st.subheader("MACD Strategy Execution Completed!")