import os
from dotenv import load_dotenv
from exchanges.bitmart_client import BitmartClient
from exchanges.topone_client import TopOneClient

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
    
    action = input("What do you want to do? (open_topone/get_balance_topone): ")

    if action.lower() == 'open_topone':
        open_position_topone(topone_client, bitmart_client)
    elif action.lower() == 'get_balance_topone':
        balance = topone_client.get_balance()
        if balance is not None:
            print(f"TopOne USDT Available Balance: {balance}")
        else:
            print("Failed to get TopOne balance.")
    else:
        print("Invalid action. Please enter 'open_topone' or 'get_balance_topone'.")