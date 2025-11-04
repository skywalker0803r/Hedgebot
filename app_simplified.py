import time
import logging
from exchanges.bitmart_client import BitmartClient
from exchanges.topone_client import TopOneClient
from strategies.voger_strategy import run_voger_strategy
import config

# 設定日誌輸出格式與等級
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    logger.info("💹 沃格(Voger)指標對沖套利策略啟動中...")

    # 初始化交易所客戶端
    bitmart_client = BitmartClient(
        api_key=config.BITMART_API_KEY,
        secret_key=config.BITMART_SECRET_KEY,
        memo=config.BITMART_MEMO
    )
    topone_client = TopOneClient(
        api_key=config.TOPONE_API_KEY,
        secret_key=config.TOPONE_SECRET_KEY
    )

    # 持續執行策略循環
    while True:
        try:
            logger.info(f"開始執行策略，交易幣種：{config.SYMBOL}...")
            results = run_voger_strategy(
                bitmart_client=bitmart_client,
                topone_client=topone_client,
                symbol=config.SYMBOL,
                margin=config.MARGIN,
                leverage=config.LEVERAGE,
                tp_percentage=config.TP_PERCENTAGE,
                sl_percentage=config.SL_PERCENTAGE,
                lookback_bars=config.LOOKBACK_BARS,
                pullback_pct=config.PULLBACK_PCT
            )

            logger.info(f"策略執行完成 ✅ 狀態：{results.get('status')}｜訊息：{results.get('message')}")
            logger.debug(f"完整回傳結果：{results}")

        except Exception as e:
            logger.error(f"⚠️ 策略執行過程中發生錯誤：{e}", exc_info=True)

        logger.info(f"🕒 等待 {config.EXECUTION_INTERVAL_SECONDS} 秒後再次執行策略...\n")
        time.sleep(config.EXECUTION_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
