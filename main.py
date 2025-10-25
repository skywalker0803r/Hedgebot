import os
from dotenv import load_dotenv
from exchanges.bitmart_client import BitmartClient
from exchanges.topone_client import TopOneClient
import time 

load_dotenv()

def open_position_topone(topone_client: TopOneClient, bitmart_client: BitmartClient):
    try:
        symbol = input("Enter symbol (e.g., BTCUSDT): ")
        side = input("Enter side (long/short): ")
        margin = float(input("Enter margin (USDT): "))
        leverage = int(input("Enter leverage: "))
        tp_percentage = float(input("Enter Take Profit percentage (e.g., 5 for 5%): "))
        sl_percentage = float(input("Enter Stop Loss percentage (e.g., 5 for 5%): "))
    except ValueError:
        print("Invalid input. Please enter correct values.")
        return

    # Get current price from Bitmart
    current_price = bitmart_client.get_current_price(symbol)
    if not current_price:
        print(f"Failed to get current price for {symbol} from Bitmart.")
        return

    print(f"Current price of {symbol} (from Bitmart) is {current_price}")
    
    if side.lower() == 'long':
        tp_price = current_price * (1 + tp_percentage / 100)
        sl_price = current_price * (1 - sl_percentage / 100)
    elif side.lower() == 'short':
        tp_price = current_price * (1 - tp_percentage / 100)
        sl_price = current_price * (1 + sl_percentage / 100)
    else:
        print(f"Invalid side: {side}. Please enter 'long' or 'short'.")
        return

    print(f"\n--- Order Summary (TopOne) ---")
    print(f"Symbol: {symbol}")
    print(f"Side: {side}")
    print(f"Margin: {margin} USDT")
    print(f"Leverage: {leverage}x")
    print(f"Take Profit: {tp_price:.4f}")
    print(f"Stop Loss: {sl_price:.4f}")
    print("---------------------")

    confirm = input("Confirm order? (y/n): ")
    if confirm.lower() != 'y':
        print("Order cancelled.")
        return

    print("\nPlacing order...")
    order_response = topone_client.place_order(
        symbol=symbol,
        side=side,
        margin=margin,
        leverage=leverage,
        tp_price=tp_price,
        sl_price=sl_price
    )

    if order_response:
        print(f"\nOrder placed successfully: {order_response}")
    else:
        print("\nFailed to place order.")

def close_position_topone(topone_client: TopOneClient):
    symbol = input("Enter symbol to close (e.g., BTCUSDT): ")
    confirm = input(f"Are you sure you want to close ALL open positions for {symbol} on TopOne? (y/n): ")
    if confirm.lower() != 'y':
        print("Close operation cancelled.")
        return

    print(f"\nClosing positions for {symbol} on TopOne...")
    responses = topone_client.close_position(symbol)
    if responses:
        for res in responses:
            if res['status'] == 'success':
                print(f"Position {res['position_id']} closed successfully: {res['response']}")
            else:
                print(f"Failed to close position {res['position_id']}: {res['message']}")
    else:
        print("No positions were closed or an error occurred.")

def run_hedge_strategy(bitmart_client: BitmartClient, topone_client: TopOneClient):
    try:
        symbol = input("Enter symbol (e.g., BTCUSDT): ")
        bitmart_side = input("Enter Bitmart side (long/short): ")
        margin = float(input("Enter margin (USDT) for each exchange: "))
        leverage = int(input("Enter leverage: "))
        tp_percentage = float(input("Enter Take Profit percentage (e.g., 5 for 5%): "))
        sl_percentage = float(input("Enter Stop Loss percentage (e.g., 5 for 5%): "))
    except ValueError:
        print("Invalid input. Please enter correct values.")
        return

    # Determine TopOne side
    topone_side = "short" if bitmart_side.lower() == "long" else "long"
    if bitmart_side.lower() not in ["long", "short"]:
        print(f"Invalid Bitmart side: {bitmart_side}. Must be 'long' or 'short'.")
        return

    # Get current price from Bitmart
    current_price = bitmart_client.get_current_price(symbol)
    if not current_price:
        print(f"Failed to get current price for {symbol} from Bitmart.")
        return

    print(f"Current price of {symbol} (from Bitmart) is {current_price}")

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

    print(f"\n--- Hedge Strategy Summary ---")
    print(f"Symbol: {symbol}")
    print(f"Bitmart Side: {bitmart_side}, TopOne Side: {topone_side}")
    print(f"Margin per exchange: {margin} USDT, Leverage: {leverage}x")
    print(f"Bitmart TP: {bitmart_tp_price:.4f}, SL: {bitmart_sl_price:.4f}")
    print(f"TopOne TP: {topone_tp_price:.4f}, SL: {topone_sl_price:.4f}")
    print("------------------------------")

    confirm = input("Confirm to run hedge strategy? (y/n): ")
    if confirm.lower() != 'y':
        print("Hedge strategy cancelled.")
        return

    print("\n--- Opening Positions ---")
    bitmart_order_response = bitmart_client.place_order(
        symbol=symbol,
        side=bitmart_side,
        margin=margin,
        leverage=leverage,
        tp_price=bitmart_tp_price,
        sl_price=bitmart_sl_price
    )
    if bitmart_order_response:
        print(f"Bitmart order placed successfully: {bitmart_order_response}")
    else:
        print("Failed to place Bitmart order.")

    topone_order_response = topone_client.place_order(
        symbol=symbol,
        side=topone_side,
        margin=margin,
        leverage=leverage,
        tp_price=topone_tp_price,
        sl_price=topone_sl_price
    )
    if topone_order_response:
        print(f"TopOne order placed successfully: {topone_order_response}")
    else:
        print("Failed to place TopOne order.")

    if not bitmart_order_response and not topone_order_response:
        print("No orders were placed. Exiting strategy.")
        return

    print("\n--- Holding positions for 1 minute ---")
    time.sleep(60)

    print("\n--- Closing Positions ---")
    bitmart_close_response = bitmart_client.close_position(symbol)
    if bitmart_close_response:
        print(f"Bitmart position closed successfully: {bitmart_close_response}")
    else:
        print("Failed to close Bitmart position.")

    topone_close_response = topone_client.close_position(symbol)
    if topone_close_response:
        print(f"TopOne position closed successfully: {topone_close_response}")
    else:
        print("Failed to close TopOne position.")

    print("\n--- Hedge Strategy Completed ---")


if __name__ == '__main__':
    bitmart_client = BitmartClient(
        api_key=os.getenv("BITMART_API_KEY"),
        secret_key=os.getenv("BITMART_SECRET_KEY"),
        memo=os.getenv("BITMART_MEMO")
    )

    topone_client = TopOneClient(
        api_key=os.getenv("TOPONE_API_KEY"),
        secret_key=os.getenv("TOPONE_SECRET_KEY"),
    )
    
    action = input("What do you want to do? (open_topone/get_balance_topone/close_topone/run_hedge): ")

    if action.lower() == 'open_topone':
        open_position_topone(topone_client, bitmart_client)
    elif action.lower() == 'get_balance_topone':
        balance = topone_client.get_balance()
        if balance is not None:
            print(f"TopOne USDT Available Balance: {balance}")
        else:
            print("Failed to get TopOne balance.")
    elif action.lower() == 'close_topone':
        close_position_topone(topone_client)
    elif action.lower() == 'run_hedge':
        run_hedge_strategy(bitmart_client, topone_client)
    else:
        print("Invalid action. Please enter 'open_topone', 'get_balance_topone', 'close_topone', or 'run_hedge'.")