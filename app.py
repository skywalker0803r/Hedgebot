import streamlit as st
import os
from dotenv import load_dotenv
from exchanges.bitmart_client import BitmartClient
from exchanges.topone_client import TopOneClient
import time
import logging
import io
import importlib

# Configure logging to capture output
log_capture_string = io.StringIO()
stream_handler = logging.StreamHandler(log_capture_string)
# Set the level for the root logger
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

st.title("Crypto Trading Strategies")

# --- Strategy Selection ---
strategy_files = [f for f in os.listdir("strategies") if f.endswith(".py") and f != "__init__.py"]
strategy_names = [f.replace(".py", "") for f in strategy_files]
selected_strategy_name = st.selectbox("Select a Strategy", strategy_names)

# Dynamically import the selected strategy
run_strategy_func = None
if selected_strategy_name:
    try:
        strategy_module = importlib.import_module(f"strategies.{selected_strategy_name}")
        # Assuming each strategy file has a function named 'run_<strategy_name>_strategy'
        strategy_function_name = f"run_{selected_strategy_name}"
        if hasattr(strategy_module, strategy_function_name):
            run_strategy_func = getattr(strategy_module, strategy_function_name)
        else:
            st.error(f"Strategy function '{strategy_function_name}' not found in '{selected_strategy_name}.py')")
    except Exception as e:
        st.error(f"Error loading strategy {selected_strategy_name}: {e}")
else:
    st.info("Please select a strategy.")

# --- Common Input Fields for Strategies ---
st.sidebar.header("Common Strategy Parameters")
symbol = st.sidebar.text_input("Symbol (e.g., BTCUSDT)", "BTCUSDT")
bitmart_side = st.sidebar.selectbox("Bitmart Side", ("long", "short"))
margin = st.sidebar.number_input("Margin (USDT) per exchange", min_value=0.1, value=10.0)
leverage = st.sidebar.number_input("Leverage", min_value=1, value=14)
tp_percentage = st.sidebar.number_input("Take Profit %", min_value=0.01, value=1.0)
sl_percentage = st.sidebar.number_input("Stop Loss %", min_value=0.01, value=1.0)

# --- Run Strategy Button ---
if st.button("Run Selected Strategy"):
    if run_strategy_func:
        st.subheader(f"Executing {selected_strategy_name} Strategy...")
        
        # Prepare common kwargs to pass to the strategy function
        common_kwargs = {
            "symbol": symbol,
            "bitmart_side": bitmart_side,
            "margin": margin,
            "leverage": leverage,
            "tp_percentage": tp_percentage,
            "sl_percentage": sl_percentage,
        }

        # Call the selected strategy function
        run_strategy_func(bitmart_client, topone_client, **common_kwargs)
    else:
        st.warning("Please select a valid strategy before running.")

# Display captured logs
with st.expander("View Logs"):
    st.code(log_capture_string.getvalue())