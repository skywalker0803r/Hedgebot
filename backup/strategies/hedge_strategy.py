import time
import logging

from exchanges.bitmart_client import BitmartClient
from exchanges.topone_client import TopOneClient

logger = logging.getLogger(__name__)

def run_hedge_strategy(bitmart_client: BitmartClient, topone_client: TopOneClient, **kwargs):
    logger.info("Running Hedge Strategy...")

    symbol = kwargs.get('symbol')
    bitmart_side = kwargs.get('bitmart_side')
    margin = kwargs.get('margin')
    leverage = kwargs.get('leverage')
    tp_percentage = kwargs.get('tp_percentage')
    sl_percentage = kwargs.get('sl_percentage')

    results = {
        "strategy": "Hedge",
        "status": "failed",
        "message": "",
        "bitmart_order": None,
        "topone_order": None,
        "bitmart_close": None,
        "topone_close": None,
    }

    # Determine TopOne side
    topone_side = "short" if bitmart_side.lower() == "long" else "long"
    if bitmart_side.lower() not in ["long", "short"]:
        logger.error(f"Invalid Bitmart side: {bitmart_side}. Must be 'long' or 'short'.")
        results["message"] = f"Invalid Bitmart side: {bitmart_side}."
        return results

    # --- Position Check ---
    bitmart_pos = bitmart_client.get_position(symbol)
    topone_pos = topone_client.get_position(symbol)
    if (bitmart_pos and bitmart_pos.get('side')) or (topone_pos and topone_pos.get('side')):
        logger.info(f"Existing position found for {symbol}. Bitmart: {bitmart_pos}, TopOne: {topone_pos}. Skipping hedge strategy.")
        results["status"] = "skipped"
        results["message"] = "Existing position found. Strategy skipped to avoid multiple positions."
        return results

    # Get current price from Bitmart
    current_price = bitmart_client.get_current_price(symbol)
    if not current_price:
        logger.error(f"Failed to get current price for {symbol} from Bitmart.")
        results["message"] = f"Failed to get current price for {symbol} from Bitmart."
        return results

    logger.info(f"Current price of {symbol} (from Bitmart) is {current_price}")

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

    logger.info("--- Hedge Strategy Summary ---")
    logger.info(f"Symbol: {symbol}")
    logger.info(f"Bitmart Side: {bitmart_side}, TopOne Side: {topone_side}")
    logger.info(f"Margin per exchange: {margin} USDT, Leverage: {leverage}x")
    logger.info(f"Bitmart TP: {bitmart_tp_price:.4f}, SL: {bitmart_sl_price:.4f}")
    logger.info(f"TopOne TP: {topone_tp_price:.4f}, SL: {topone_sl_price:.4f}")

    logger.info("Opening Positions...")
    bitmart_order_response = bitmart_client.place_order(
        symbol=symbol,
        side=bitmart_side,
        margin=margin,
        leverage=leverage,
        tp_price=bitmart_tp_price,
        sl_price=bitmart_sl_price
    )
    if bitmart_order_response:
        logger.info(f"Bitmart order placed successfully: {bitmart_order_response}")
        results["bitmart_order"] = bitmart_order_response
    else:
        logger.error("Failed to place Bitmart order.")
        results["message"] = "Failed to place Bitmart order."

    topone_order_response = topone_client.place_order(
        symbol=symbol,
        side=topone_side,
        margin=margin,
        leverage=leverage,
        tp_price=topone_tp_price,
        sl_price=topone_sl_price
    )
    if topone_order_response:
        logger.info(f"TopOne order placed successfully: {topone_order_response}")
        results["topone_order"] = topone_order_response
    else:
        logger.error("Failed to place TopOne order.")
        results["message"] += " Failed to place TopOne order."

    if not bitmart_order_response and not topone_order_response:
        logger.warning("No orders were placed. Exiting strategy.")
        results["message"] = "No orders were placed."
        return results

    logger.info("Holding positions for 1 minute...")
    time.sleep(60)

    logger.info("Closing Positions...")
    bitmart_close_response = bitmart_client.close_position(symbol)
    if bitmart_close_response:
        logger.info(f"Bitmart position closed successfully: {bitmart_close_response}")
        results["bitmart_close"] = bitmart_close_response
    else:
        logger.error("Failed to close Bitmart position.")
        results["message"] += " Failed to close Bitmart position."

    topone_close_response = topone_client.close_position(symbol)
    if topone_close_response:
        logger.info(f"TopOne position closed successfully: {topone_close_response}")
        results["topone_close"] = topone_close_response
    else:
        logger.error("Failed to close TopOne position.")
        results["message"] += " Failed to close TopOne position."

    results["status"] = "completed"
    results["message"] = "Hedge strategy completed."
    logger.info("Hedge Strategy Completed!")
    return results