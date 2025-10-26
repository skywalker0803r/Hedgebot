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
import uuid # For unique filenames
import tempfile # For temporary file creation

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

st.title("加密貨幣交易策略 (後端控制)")

# --- Strategy Selection ---
strategy_files = [f for f in os.listdir("strategies") if f.endswith(".py") and f != "__init__.py"]
strategy_names = [f.replace(".py", "") for f in strategy_files]
selected_strategy_name = st.selectbox("選擇策略", strategy_names)

# --- Common Input Fields for Strategies ---
st.sidebar.header("策略參數")
symbol = st.sidebar.text_input("交易對 (例如: XRPUSDT)", "XRPUSDT")
bitmart_side = st.sidebar.selectbox("Bitmart 方向", ("long", "short"))
margin = st.sidebar.number_input("每交易所保證金 (USDT)", min_value=0.1, value=1.0)
leverage = st.sidebar.number_input("槓桿", min_value=1, value=69)
tp_percentage = st.sidebar.number_input("止盈 %", min_value=0.01, value=0.2)
sl_percentage = st.sidebar.number_input("止損 %", min_value=0.01, value=2.0)

# --- Backend Control Parameters ---
st.sidebar.header("後端控制")
polling_interval = st.sidebar.number_input("輪詢間隔 (秒)", min_value=10, value=60)
countdown_placeholder = st.sidebar.empty()
max_execution_rounds = st.sidebar.number_input("最大執行回合數 (-1 為無限)", min_value=-1, value=-1)
progress_bar_placeholder = st.sidebar.empty()

# --- Backend Control Parameters ---
if 'backend_process_pid' not in st.session_state:
    st.session_state.backend_process_pid = None
if 'progress_file_path' not in st.session_state:
    st.session_state.progress_file_path = None
if 'last_poll_time' not in st.session_state:
    st.session_state.last_poll_time = None
if 'log_subheader_initialized' not in st.session_state:
    st.session_state.log_subheader_initialized = False
if 'backend_log_placeholder' not in st.session_state:
    st.session_state.backend_log_placeholder = None

def start_backend():
    if st.session_state.backend_process_pid:
        try:
            os.kill(st.session_state.backend_process_pid, 0) 
            st.warning(f"後端服務已在運行，PID: {st.session_state.backend_process_pid}。")
            return
        except OSError:
            st.session_state.backend_process_pid = None

    # Generate a unique progress file path
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
        st.session_state.progress_file_path = f.name

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
            [sys.executable, "backend_service.py", params_json, st.session_state.progress_file_path],
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL, 
        )
        st.session_state.backend_process_pid = process.pid
        st.success(f"後端服務已啟動，PID: {process.pid}")
        logger_app.info(f"Backend service started with PID: {process.pid}")
        st.session_state.last_poll_time = time.time()
    except Exception as e:
        st.error(f"啟動後端服務失敗: {e}")
        logger_app.error(f"Failed to start backend service: {e}")

def stop_backend():
    if st.session_state.backend_process_pid:
        # Attempt to close all positions before stopping the backend process
        close_all_positions(bitmart_client, topone_client, symbol)

        try:
            os.kill(st.session_state.backend_process_pid, 9) 
            st.success(f"後端服務 (PID: {st.session_state.backend_process_pid}) 已停止。")
            logger_app.info(f"Backend service with PID {st.session_state.backend_process_pid} stopped.")
            st.session_state.backend_process_pid = None
            if st.session_state.progress_file_path and os.path.exists(st.session_state.progress_file_path):
                os.remove(st.session_state.progress_file_path)
                st.session_state.progress_file_path = None
            st.session_state.last_poll_time = None
        except OSError as e:
            st.error(f"停止後端服務失敗 (PID: {st.session_state.backend_process_pid}): {e}")
            logger_app.error(f"Failed to stop backend service (PID: {st.session_state.backend_process_pid}): {e}")
            st.session_state.backend_process_pid = None 
    else:
        st.info("後端服務未運行。")

def update_backend_logs():
    if st.session_state.backend_log_placeholder:
        try:
            with open("backend_logs.txt", "r") as f:
                logs = f.read()
                st.session_state.backend_log_placeholder.code(logs)
        except FileNotFoundError:
            st.session_state.backend_log_placeholder.code("後端日誌檔案未找到。服務可能尚未啟動。")
        except Exception as e:
            st.session_state.backend_log_placeholder.error(f"讀取後端日誌時出錯: {e}")

def update_progress_bar():
    if st.session_state.progress_file_path and os.path.exists(st.session_state.progress_file_path):
        try:
            with open(st.session_state.progress_file_path, "r") as f:
                content = f.read().strip()
                if content:
                    current_round = int(content)
                else:
                    current_round = 0 # Default to 0 if file is empty
            
            if max_execution_rounds == -1:
                progress_bar_placeholder.progress(0, text=f"當前回合: {current_round} (無限模式)")
            else:
                progress_percent = min(current_round / max_execution_rounds, 1.0)
                progress_bar_placeholder.progress(progress_percent, text=f"當前回合: {current_round} / {max_execution_rounds}")
        except ValueError:
            progress_bar_placeholder.warning("進度檔案內容無效，等待有效進度...")
        except Exception as e:
            progress_bar_placeholder.error(f"讀取進度檔案時出錯: {e}")
    else:
        progress_bar_placeholder.progress(0, text="進度: 未啟動")

def update_countdown():
    if st.session_state.backend_process_pid and st.session_state.last_poll_time:
        time_elapsed = time.time() - st.session_state.last_poll_time
        time_remaining = int(polling_interval - (time_elapsed % polling_interval))
        countdown_placeholder.info(f"下次輪詢倒計時: {time_remaining} 秒")
    else:
        countdown_placeholder.info("倒計時: 未啟動")

def close_all_positions(bitmart_client, topone_client, symbol):
    logger_app.info(f"嘗試平倉 {symbol} 在 Bitmart 和 TopOne 上的所有倉位...")
    st.info(f"嘗試平倉 {symbol} 在 Bitmart 和 TopOne 上的所有倉位...")

    # Close positions on Bitmart
    bitmart_result = bitmart_client.close_position(symbol)
    if bitmart_result:
        logger_app.info(f"Bitmart 倉位平倉結果: {bitmart_result}")
        st.success(f"Bitmart 倉位平倉成功: {bitmart_result}")
    else:
        logger_app.warning(f"Bitmart 上沒有 {symbol} 的倉位或平倉失敗。")
        st.warning(f"Bitmart 上沒有 {symbol} 的倉位或平倉失敗。")

    # Close positions on TopOne
    topone_result = topone_client.close_position(symbol)
    if topone_result:
        logger_app.info(f"TopOne 倉位平倉結果: {topone_result}")
        st.success(f"TopOne 倉位平倉成功: {topone_result}")
    else:
        logger_app.warning(f"TopOne 上沒有 {symbol} 的倉位或平倉失敗。")
        st.warning(f"TopOne 上沒有 {symbol} 的倉位或平倉失敗。")

    logger_app.info(f"{symbol} 倉位平倉嘗試完成。")
    st.info(f"{symbol} 倉位平倉嘗試完成。")

col1, col2 = st.columns(2)
with col1:
    if st.button("啟動策略"):
        start_backend()
        update_progress_bar()
        update_countdown()
with col2:
    if st.button("停止策略"):
        stop_backend()

# --- Display Backend Logs ---
if not st.session_state.log_subheader_initialized:
    st.subheader("後端服務日誌")
    st.session_state.backend_log_placeholder = st.empty()
    st.session_state.log_subheader_initialized = True

update_backend_logs()
update_progress_bar()
update_countdown()

# --- Auto-refresh mechanism ---
if st.session_state.backend_process_pid:
    time.sleep(1) # Wait for 1 second
    st.rerun()