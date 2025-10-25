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
        logging.FileHandler(log_file_path, mode='w'), 
        logging.StreamHandler() 
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

def run_strategy_continuously(strategy_name: str, interval_seconds: int, max_rounds: int = -1, **strategy_kwargs):
    logger.info(f"Starting continuous execution of {strategy_name} strategy.")
    logger.info(f"Polling interval: {interval_seconds} seconds, Max rounds: {max_rounds}")

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
        logger.error(f"Error loading strategy {strategy_name}: {e}")
        return

    round_count = 0
    while True:
        round_count += 1
        logger.info(f"--- Running round {round_count} for {strategy_name} strategy ---")

        # --- Implement check for insufficient margin ---
        required_margin = strategy_kwargs.get('margin')
        if required_margin is None:
            logger.error("Strategy parameter 'margin' is missing. Cannot check for insufficient margin.")
            break

        bitmart_balance = bitmart_client.get_balance()
        topone_balance = topone_client.get_balance()

        if bitmart_balance is None or topone_balance is None:
            logger.error("Failed to retrieve balance from one or both exchanges. Cannot check for insufficient margin.")
            break

        logger.info(f"Bitmart available balance: {bitmart_balance:.2f} USDT, TopOne available balance: {topone_balance:.2f} USDT")

        if bitmart_balance < required_margin:
            logger.error(f"Insufficient margin on Bitmart. Required: {required_margin:.2f}, Available: {bitmart_balance:.2f}. Stopping strategy.")
            break
        if topone_balance < required_margin:
            logger.error(f"Insufficient margin on TopOne. Required: {required_margin:.2f}, Available: {topone_balance:.2f}. Stopping strategy.")
            break
        # --- End of insufficient margin check ---

        # Execute the strategy
        results = run_strategy_func(bitmart_client, topone_client, **strategy_kwargs)
        logger.info(f"Strategy results for round {round_count}: {results}")

        # Check stopping conditions
        if max_rounds != -1 and round_count >= max_rounds:
            logger.info(f"Max rounds ({max_rounds}) reached. Stopping strategy.")
            break
        
        logger.info(f"Waiting for {interval_seconds} seconds before next round...")
        time.sleep(interval_seconds)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        try:
            params_json = sys.argv[1]
            strategy_config = json.loads(params_json)

            strategy_to_run = strategy_config["strategy_name"]
            polling_interval = strategy_config["interval_seconds"]
            max_execution_rounds = strategy_config["max_rounds"]
            strategy_params = strategy_config["kwargs"]

            run_strategy_continuously(strategy_to_run, polling_interval, max_execution_rounds, **strategy_params)
        except Exception as e:
            logger.error(f"Error parsing command-line arguments or running strategy: {e}")
    else:
        logger.error("No strategy configuration provided. Please run with JSON arguments.")
