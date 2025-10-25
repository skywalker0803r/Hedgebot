import io
import streamlit as st
import os
from dotenv import load_dotenv
from exchanges.bitmart_client import BitmartClient
from exchanges.topone_client import TopOneClient
import time
import logging

# Configure logging to capture output
log_capture_string = io.StringIO()
stream_handler = logging.StreamHandler(log_capture_string)
logging.basicConfig(level=logging.INFO, handlers=[stream_handler])

# Load environment variables
load_dotenv()

# Initialize clients (using st.session_state to avoid re-initialization on rerun)
if 'bitmart_client' not in st.session_state:
    st.session_state.bitmart_client = BitmartClient(
        api_key=os.getenv("BITMART_API_KEY"),
        secret_key=os.getenv("BITMART_SECRET_KEY"),
        memo=os.getenv("BITMART_MEMO")
    )
if 'topone_client' not in st.session_state:
    st.session_state.topone_client = TopOneClient(
        api_key=os.getenv("TOPONE_API_KEY"),
        secret_key=os.getenv("TOPONE_SECRET_KEY"),
    )

bitmart_client = st.session_state.bitmart_client
topone_client = st.session_state.topone_client

st.title("Crypto Hedging Strategy")

# Input fields
symbol = st.text_input("Enter symbol (e.g., BTCUSDT)", "BTCUSDT")
bitmart_side = st.selectbox("Enter Bitmart side", ("long", "short"))
margin = st.number_input("Enter margin (USDT) for each exchange", min_value=0.1, value=10.0)
leverage = st.number_input("Enter leverage", min_value=1, value=14)
tp_percentage = st.number_input("Enter Take Profit percentage (e.g., 1 for 1%)", min_value=0.01, value=1.0)
sl_percentage = st.number_input("Enter Stop Loss percentage (e.g., 1 for 1%)", min_value=0.01, value=1.0)

if st.button("Run Hedge Strategy"):
    st.subheader("Running Hedge Strategy...")
    
    # Determine TopOne side
    topone_side = "short" if bitmart_side.lower() == "long" else "long"

    # Get current price from Bitmart
    current_price = bitmart_client.get_current_price(symbol)
    if not current_price:
        st.error(f"Failed to get current price for {symbol} from Bitmart.")
        st.stop()

    st.write(f"Current price of {symbol} (from Bitmart) is {current_price}")

    # Calculate TP/SL for Bitmart
    if bitmart_side.lower() == 'long':
        bitmart_tp_price = current_price * (1 + tp_percentage / 100)
        bitmart_sl_price = current_price * (1 - sl_percentage / 100)
    else: # short
        bitmart_tp_price = current_price * (1 - tp_percentage / 100)
        bitmart_sl_price = current_price * (1 + sl_percentage / 100)

    # Calculate TP/SL for TopOne (opposite side)
    if topone_side.lower() == 'long':
        topone_tp_price = current_price * (1 + tp_percentage / 100)
        topone_sl_price = current_price * (1 - sl_percentage / 100)
    else: # short
        topone_tp_price = current_price * (1 - tp_percentage / 100)
        topone_sl_price = current_price * (1 + sl_percentage / 100)

    st.subheader("Hedge Strategy Summary")
    st.write(f"Symbol: {symbol}")
    st.write(f"Bitmart Side: {bitmart_side}, TopOne Side: {topone_side}")
    st.write(f"Margin per exchange: {margin} USDT, Leverage: {leverage}x")
    st.write(f"Bitmart TP: {bitmart_tp_price:.4f}, SL: {bitmart_sl_price:.4f}")
    st.write(f"TopOne TP: {topone_tp_price:.4f}, SL: {topone_sl_price:.4f}")

    st.subheader("Opening Positions...")
    bitmart_order_response = bitmart_client.place_order(
        symbol=symbol,
        side=bitmart_side,
        margin=margin,
        leverage=leverage,
        tp_price=bitmart_tp_price,
        sl_price=bitmart_sl_price
    )
    if bitmart_order_response:
        st.success(f"Bitmart order placed successfully: {bitmart_order_response}")
    else:
        st.error("Failed to place Bitmart order.")

    topone_order_response = topone_client.place_order(
        symbol=symbol,
        side=topone_side,
        margin=margin,
        leverage=leverage,
        tp_price=topone_tp_price,
        sl_price=topone_sl_price
    )
    if topone_order_response:
        st.success(f"TopOne order placed successfully: {topone_order_response}")
    else:
        st.error("Failed to place TopOne order.")

    if not bitmart_order_response and not topone_order_response:
        st.warning("No orders were placed. Exiting strategy.")
    else:
        st.info("Holding positions for 1 minute...")
        time.sleep(60)

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

    st.subheader("Hedge Strategy Completed!")

# Display captured logs
with st.expander("View Logs"):
    st.code(log_capture_string.getvalue())
