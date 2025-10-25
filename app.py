import streamlit as st
import os
from dotenv import load_dotenv
from exchanges.bitmart_client import BitmartClient
from exchanges.topone_client import TopOneClient
import time
import logging
import io
import importlib
import subprocess 
import json 
import sys # Import sys to get the Python executable

# --- Logging Setup for Streamlit App ---
# This is for the Streamlit app's own logs, not the backend service's logs
log_capture_string_app = io.StringIO()
stream_handler_app = logging.StreamHandler(log_capture_string_app)
logging.basicConfig(level=logging.INFO, handlers=[stream_handler_app], force=True) 
logger_app = logging.getLogger(__name__)

# --- Environment Variables ---
load_dotenv()

# --- Client Initialization (cached) ---
@st.cache_resource
def init_clients():
    bitmart_client = BitmartClient(
        api_key=os.getenv("BITMART_API_KEY"),
        secret_key=os.getenv("BITMART_SECRET_KEY"),
        memo=os.getenv("BITMART_MEMO")
    )
    topone_client = TopOneClient(
        api_key=os.getenv("TOPONE_API_KEY"),
        secret_key=os.getenv("TOPONE_SECRET_KEY"),
    )
    return bitmart_client, topone_client

# We don't need to initialize clients here if they are only used by the backend.
# But for displaying current price or other info in Streamlit, we might need them.
# For now, let's keep them for potential future use in Streamlit itself.
bitmart_client, topone_client = init_clients()

st.title("Crypto Trading Strategies (Backend Controlled)")

# --- Strategy Selection ---
strategy_files = [f for f in os.listdir("strategies") if f.endswith(".py") and f != "__init__.py"]
strategy_names = [f.replace(".py", "") for f in strategy_files]
selected_strategy_name = st.selectbox("Select a Strategy", strategy_names)

# --- Common Input Fields for Strategies ---
st.sidebar.header("Strategy Parameters")
symbol = st.sidebar.text_input("Symbol (e.g., BTCUSDT)", "BTCUSDT")
bitmart_side = st.sidebar.selectbox("Bitmart Side", ("long", "short"))
margin = st.sidebar.number_input("Margin (USDT) per exchange", min_value=0.1, value=10.0)
leverage = st.sidebar.number_input("Leverage", min_value=1, value=14)
tp_percentage = st.sidebar.number_input("Take Profit %", min_value=0.01, value=1.0)
sl_percentage = st.sidebar.number_input("Stop Loss %", min_value=0.01, value=1.0)

# --- Backend Control Parameters ---
st.sidebar.header("Backend Control")
polling_interval = st.sidebar.number_input("Polling Interval (seconds)", min_value=10, value=60)
max_execution_rounds = st.sidebar.number_input("Max Execution Rounds (-1 for infinite)", min_value=-1, value=5)

# --- Backend Process Management ---
if 'backend_process_pid' not in st.session_state:
    st.session_state.backend_process_pid = None

def start_backend():
    if st.session_state.backend_process_pid:
        try:
            os.kill(st.session_state.backend_process_pid, 0) 
            st.warning(f"Backend service is already running with PID: {st.session_state.backend_process_pid}.")
            return
        except OSError:
            st.session_state.backend_process_pid = None

    strategy_params = {
        "strategy_name": selected_strategy_name,
        "interval_seconds": polling_interval,
        "max_rounds": max_execution_rounds,
        "kwargs": {
            "symbol": symbol,
            "bitmart_side": bitmart_side,
            "margin": margin,
            "leverage": leverage,
            "tp_percentage": tp_percentage,
            "sl_percentage": sl_percentage,
        }
    }
    params_json = json.dumps(strategy_params)

    try:
        process = subprocess.Popen(
            [sys.executable, "backend_service.py", params_json],
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL, 
        )
        st.session_state.backend_process_pid = process.pid
        st.success(f"Backend service started with PID: {process.pid}")
        logger_app.info(f"Backend service started with PID: {process.pid}")
    except Exception as e:
        st.error(f"Failed to start backend service: {e}")
        logger_app.error(f"Failed to start backend service: {e}")

def stop_backend():
    if st.session_state.backend_process_pid:
        try:
            os.kill(st.session_state.backend_process_pid, 9) 
            st.success(f"Backend service with PID {st.session_state.backend_process_pid} stopped.")
            logger_app.info(f"Backend service with PID {st.session_state.backend_process_pid} stopped.")
            st.session_state.backend_process_pid = None
        except OSError as e:
            st.error(f"Failed to stop backend service (PID: {st.session_state.backend_process_pid}): {e}")
            logger_app.error(f"Failed to stop backend service (PID: {st.session_state.backend_process_pid}): {e}")
            st.session_state.backend_process_pid = None 
    else:
        st.info("Backend service is not running.")

col1, col2 = st.columns(2)
with col1:
    if st.button("Start Strategy"):
        start_backend()
with col2:
    if st.button("Stop Strategy"):
        stop_backend()

# --- Display Backend Logs ---
st.subheader("Backend Service Logs")
backend_log_placeholder = st.empty()

def update_backend_logs():
    try:
        with open("backend_logs.txt", "r") as f:
            logs = f.read()
            backend_log_placeholder.code(logs)
    except FileNotFoundError:
        backend_log_placeholder.code("Backend logs file not found. Service might not have started yet.")
    except Exception as e:
        backend_log_placeholder.error(f"Error reading backend logs: {e}")

if st.button("Refresh Backend Logs"):
    update_backend_logs()

update_backend_logs()

# --- Streamlit App's Own Logs ---
with st.expander("View Streamlit App Logs"):
    st.code(log_capture_string_app.getvalue())