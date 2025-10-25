import streamlit as st
from exchanges.bitmart_client import BitmartClient
from exchanges.topone_client import TopOneClient

def run_rsi_strategy(bitmart_client: BitmartClient, topone_client: TopOneClient, **kwargs):
    st.info("RSI Strategy selected. (Not yet implemented)")
    st.write("This strategy will monitor RSI. If RSI < 20, open position. If RSI > 80, close position.")
    st.write(f"Received parameters: {kwargs}")
