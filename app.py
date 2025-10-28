import streamlit as st
import os
import json
import time
import subprocess
import tempfile
import sys
import logging
import io
from dotenv import load_dotenv
from exchanges.bitmart_client import BitmartClient
from exchanges.topone_client import TopOneClient

# ==============================
# 🔧 初始化
# ==============================

st.set_page_config(page_title="加密貨幣交易策略控制面板", layout="wide")
load_dotenv()

# --- Logging Setup ---
log_buffer = io.StringIO()
logging.basicConfig(stream=log_buffer, level=logging.INFO, force=True, encoding='utf-8')
logger = logging.getLogger(__name__)

# --- 初始化交易所客戶端（使用 Streamlit cache） ---
@st.cache_resource
def init_clients():
    return (
        BitmartClient(
            api_key=os.getenv("BITMART_API_KEY"),
            secret_key=os.getenv("BITMART_SECRET_KEY"),
            memo=os.getenv("BITMART_MEMO"),
        ),
        TopOneClient(
            api_key=os.getenv("TOPONE_API_KEY"),
            secret_key=os.getenv("TOPONE_SECRET_KEY"),
        ),
    )

bitmart, topone = init_clients()

# --- Session 狀態 ---
defaults = {
    "backend_pid": None,
    "progress_file": None,
    "last_poll": None,
}
for k, v in defaults.items():
    st.session_state.setdefault(k, v)

# ==============================
# 🎯 UI - 主介面
# ==============================

st.title("💹 加密貨幣交易策略控制面板")

# --- 選擇策略 ---
strategy_dir = "strategies"
strategies = [f[:-3] for f in os.listdir(strategy_dir) if f.endswith(".py") and f != "__init__.py"]
selected_strategy = st.selectbox("選擇策略", strategies)

# --- 參數設定 ---
with st.sidebar:
    st.header("策略參數設定")
    params = {
        "symbol": st.text_input("交易對", "XRPUSDT"),
        "bitmart_side": st.selectbox("Bitmart 方向", ("long", "short")),
        "margin": st.number_input("每交易所保證金 (USDT)", min_value=0.1, value=1.0),
        "leverage": st.number_input("槓桿", min_value=1, value=69),
        "tp_percentage": st.number_input("止盈 %", min_value=0.01, value=0.2),
        "sl_percentage": st.number_input("止損 %", min_value=0.01, value=1.0),
    }

    st.header("後端執行控制")
    interval = st.number_input("輪詢間隔 (秒)", min_value=10, value=180)
    max_rounds = st.number_input("最大執行回合 (-1 為無限)", min_value=-1, value=-1)

# ==============================
# ⚙️ 功能函式
# ==============================

def is_backend_running():
    pid = st.session_state.backend_pid
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False

def start_backend():
    if is_backend_running():
        st.warning(f"後端服務已運行 (PID: {st.session_state.backend_pid})")
        return

    # 建立臨時進度檔
    tmp = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt")
    st.session_state.progress_file = tmp.name

    payload = json.dumps({
        "strategy_name": selected_strategy,
        "interval_seconds": interval,
        "max_rounds": max_rounds,
        "kwargs": params,
    })

    try:
        proc = subprocess.Popen(
            [sys.executable, "backend_service.py", payload, tmp.name],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        st.session_state.backend_pid = proc.pid
        st.session_state.last_poll = time.time()
        st.success(f"✅ 後端啟動成功 (PID: {proc.pid})")
        logger.info(f"Backend started PID={proc.pid}")
    except Exception as e:
        st.error(f"啟動後端失敗: {e}")
        logger.error(e)

def stop_backend():
    pid = st.session_state.backend_pid
    if not pid:
        st.info("後端未運行")
        return

    # 嘗試平倉
    for name, client in [("Bitmart", bitmart), ("TopOne", topone)]:
        res = client.close_position(params["symbol"])
        st.info(f"{name} 平倉結果: {res}")

    try:
        os.kill(pid, 9)
        st.success(f"🛑 已停止後端服務 (PID: {pid})")
    except OSError as e:
        st.warning(f"停止失敗: {e}")
    finally:
        # 清理狀態
        st.session_state.backend_pid = None
        if st.session_state.progress_file and os.path.exists(st.session_state.progress_file):
            os.remove(st.session_state.progress_file)
        st.session_state.progress_file = None

def read_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return None

def render_progress():
    file = st.session_state.progress_file
    if not file or not os.path.exists(file):
        st.progress(0, text="進度: 未啟動")
        return
    data = read_file(file)
    try:
        current = int(data) if data else 0
        if max_rounds == -1:
            st.progress(0, text=f"回合: {current} (無限)")
        else:
            st.progress(min(current / max_rounds, 1.0), text=f"回合: {current}/{max_rounds}")
    except ValueError:
        st.warning("進度檔內容無效")

def render_countdown():
    if not is_backend_running():
        st.info("倒計時: 未啟動")
        return
    elapsed = time.time() - st.session_state.last_poll
    remain = int(interval - (elapsed % interval))
    st.info(f"⏳ 下次輪詢: {remain} 秒")

# ==============================
# 🧭 主介面動作控制
# ==============================

col1, col2 = st.columns(2)
with col1:
    if st.button("🚀 啟動策略"):
        start_backend()
with col2:
    if st.button("🛑 停止策略"):
        stop_backend()

st.divider()

st.subheader("📜 後端日誌")
backend_log = read_file("backend_logs.txt") or "尚無日誌"
st.code(backend_log, language="bash")

render_progress()
render_countdown()

# 自動刷新 (若後端正在執行)
if is_backend_running():
    time.sleep(1)
    st.rerun()
