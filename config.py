# config.py

# 交易所 API 憑證（請替換為你實際的 API Key）
BITMART_API_KEY = "YOUR_BITMART_API_KEY"
BITMART_SECRET_KEY = "YOUR_BITMART_SECRET_KEY"
BITMART_MEMO = "YOUR_BITMART_MEMO"  # 可選，若 Bitmart 需要則填入

TOPONE_API_KEY = "YOUR_TOPONE_API_KEY"
TOPONE_SECRET_KEY = "YOUR_TOPONE_SECRET_KEY"

# 策略參數設定
SYMBOL = "ETHUSDT"      # 交易對
MARGIN = 5              # 每筆交易的保證金金額
LEVERAGE = 1            # 槓桿倍數
TP_PERCENTAGE = 2.0      # 止盈百分比（%）
SL_PERCENTAGE = 1.0      # 止損百分比（%）
LOOKBACK_BARS = 5        # 用於訊號產生的回看K線數量
PULLBACK_PCT = 0.01      # 用於回調觸發的百分比（1%）

# 策略執行頻率（秒）
EXECUTION_INTERVAL_SECONDS = 60  # 每隔幾秒執行一次策略

# Debug Mode
DEBUG_MODE = False
