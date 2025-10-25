import os
from dotenv import load_dotenv
from exchanges.bitmart_client import BitmartClient

load_dotenv()

def open_position(client: BitmartClient):
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

    current_price = client.get_current_price(symbol)
    if not current_price:
        print(f"\nFailed to get current price for {symbol}")
        return

    print(f"Current price of {symbol} is {current_price}")
    
    if side.lower() == 'long':
        tp_price = current_price * (1 + tp_percentage / 100)
        sl_price = current_price * (1 - sl_percentage / 100)
    elif side.lower() == 'short':
        tp_price = current_price * (1 - tp_percentage / 100)
        sl_price = current_price * (1 + sl_percentage / 100)
    else:
        print(f"Invalid side: {side}. Please enter 'long' or 'short'.")
        return

    print(f"\n--- Order Summary ---")
    print(f"Symbol: {symbol}")
    print(f"Side: {side}")
    print(f"Margin: {margin} USDT")
    print(f"Leverage: {leverage}x")
    # The client will handle the final rounding
    print(f"Approx. Take Profit: {tp_price:.4f}")
    print(f"Approx. Stop Loss: {sl_price:.4f}")
    print("---------------------")

    confirm = input("Confirm order? (y/n): ")
    if confirm.lower() != 'y':
        print("Order cancelled.")
        return

    print("\nPlacing order...")
    order_response = client.place_order(
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

def close_position(client: BitmartClient):
    symbol = input("Enter symbol to close (e.g., BTCUSDT): ")
    confirm = input(f"Are you sure you want to close the position for {symbol}? (y/n): ")
    if confirm.lower() != 'y':
        print("Close operation cancelled.")
        return

    print(f"\nClosing position for {symbol}...")
    response = client.close_position(symbol)
    if response:
        print(f"\nClose order placed successfully: {response}")
    else:
        print("\nFailed to place close order.")

if __name__ == '__main__':
    client = BitmartClient(
        api_key=os.getenv("BITMART_API_KEY"),
        secret_key=os.getenv("BITMART_SECRET_KEY"),
        memo=os.getenv("BITMART_MEMO")
    )
    
    action = input("What do you want to do? (open/close): ")

    if action.lower() == 'open':
        open_position(client)
    elif action.lower() == 'close':
        close_position(client)
    else:
        print("Invalid action. Please enter 'open' or 'close'.")
