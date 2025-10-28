import os
import time
import logging
import importlib
import sys 
import json 
from dotenv import load_dotenv

from exchanges.bitmart_client import BitmartClient
from exchanges.topone_client import TopOneClient

# Configure logging for the backend service
log_file_path = "backend_logs.txt"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file_path, mode='w',encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

def run_strategy_continuously(strategy_name: str, interval_seconds: int, max_rounds: int = -1, progress_file_path: str = None, **strategy_kwargs):
    logger.info(f"開始持續執行 {strategy_name} 策略。")
    logger.info(f"輪詢間隔: {interval_seconds} 秒, 最大回合: {max_rounds}")

    # Initialize clients
    bitmart_client = BitmartClient(
        api_key=os.getenv("BITMART_API_KEY"),
        secret_key=os.getenv("BITMART_SECRET_KEY"),
        memo=os.getenv("BITMART_MEMO")
    )
    topone_client = TopOneClient(
        api_key=os.getenv("TOPONE_API_KEY"),
        secret_key=os.getenv("TOPONE_SECRET_KEY"),
    )

    # Dynamically import the selected strategy
    try:
        strategy_module = importlib.import_module(f"strategies.{strategy_name}")
        strategy_function_name = f"run_{strategy_name}"
        run_strategy_func = getattr(strategy_module, strategy_function_name)
    except Exception as e:
        logger.error(f"加載策略 {strategy_name} 時出錯: {e}")
        return

    round_count = 0
    while True:
        round_count += 1
        if progress_file_path:
            try:
                with open(progress_file_path, "w") as f:
                    f.write(str(round_count))
            except Exception as e:
                logger.error(f"Error writing progress to file {progress_file_path}: {e}")

        logger.info(f"--- 執行 {strategy_name} 策略 第 {round_count} 回合 ---")

        # --- Implement check for insufficient margin ---
        required_margin = strategy_kwargs.get('margin')
        if required_margin is None:
            logger.error("策略參數 'margin' 缺失。無法檢查保證金是否不足。")
            break

        bitmart_balance = bitmart_client.get_balance()
        topone_balance = topone_client.get_balance()

        if bitmart_balance is None or topone_balance is None:
            logger.error("無法從一個或兩個交易所獲取餘額。無法檢查保證金是否不足。")
            break

        logger.info(f"Bitmart 可用餘額: {bitmart_balance:.2f} USDT, TopOne 可用餘額: {topone_balance:.2f} USDT")

        if bitmart_balance < required_margin:
            logger.error(f"Bitmart 保證金不足。需要: {required_margin:.2f}, 可用: {bitmart_balance:.2f}。停止策略。")
            break
        if topone_balance < required_margin:
            logger.error(f"TopOne 保證金不足。需要: {required_margin:.2f}, 可用: {topone_balance:.2f}。停止策略。")
            break
        # --- End of insufficient margin check ---

        # Execute the strategy
        results = run_strategy_func(bitmart_client, topone_client, **strategy_kwargs)
        logger.info(f"第 {round_count} 回合的策略結果: {results}")

        # Check stopping conditions
        if max_rounds != -1 and round_count >= max_rounds:
            logger.info(f"已達到最大回合數 ({max_rounds})。停止策略。")
            break
        
        logger.info(f"等待 {interval_seconds} 秒後進入下一回合...")
        time.sleep(interval_seconds)

if __name__ == "__main__":
    if len(sys.argv) > 2:
        try:
            params_json = sys.argv[1]
            progress_file_path = sys.argv[2]
            strategy_config = json.loads(params_json)

            strategy_to_run = strategy_config["strategy_name"]
            polling_interval = strategy_config["interval_seconds"]
            max_execution_rounds = strategy_config["max_rounds"]
            strategy_params = strategy_config["kwargs"]

            run_strategy_continuously(strategy_to_run, polling_interval, max_execution_rounds, progress_file_path, **strategy_params)
        except Exception as e:
            logger.error(f"解析命令行參數或運行策略時出錯: {e}")
    else:
        logger.error("未提供策略配置或進度檔案路徑。請使用 JSON 參數和進度檔案路徑運行。")
