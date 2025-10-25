import streamlit as st
from exchanges.bitmart_client import BitmartClient
from exchanges.topone_client import TopOneClient

def run_macd_strategy(bitmart_client: BitmartClient, topone_client: TopOneClient, **kwargs):
    st.info("MACD Strategy selected. (Not yet implemented)")
    st.write("This strategy will monitor MACD for a golden cross to open a position and a death cross to close.")
    st.write(f"Received parameters: {kwargs}")
