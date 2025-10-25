import os
from dotenv import load_dotenv
from exchanges.bitmart_client import BitmartClient

load_dotenv()

if __name__ == '__main__':
    client = BitmartClient(
        api_key=os.getenv("BITMART_API_KEY"),
        secret_key=os.getenv("BITMART_SECRET_KEY"),
        memo=os.getenv("BITMART_MEMO")
    )
    
    try:
        symbol = input("Enter symbol (e.g., BTCUSDT): ")
        side = input("Enter side (long/short): ")
        margin = float(input("Enter margin (USDT): "))
        leverage = int(input("Enter leverage: "))
        tp_percentage = float(input("Enter Take Profit percentage (e.g., 5 for 5%): "))
        sl_percentage = float(input("Enter Stop Loss percentage (e.g., 5 for 5%): "))
    except ValueError:
        print("Invalid input. Please enter correct values.")
        exit()

    current_price = client.get_current_price(symbol)
    if current_price:
        print(f"Current price of {symbol} is {current_price}")
        
        if side.lower() == 'long':
            tp_price = round(current_price * (1 + tp_percentage / 100), 2)
            sl_price = round(current_price * (1 - sl_percentage / 100), 2)
        elif side.lower() == 'short':
            tp_price = round(current_price * (1 - tp_percentage / 100), 2)
            sl_price = round(current_price * (1 + sl_percentage / 100), 2)
        else:
            print(f"Invalid side: {side}. Please enter 'long' or 'short'.")
            exit()

        print(f"\n--- Order Summary ---")
        print(f"Symbol: {symbol}")
        print(f"Side: {side}")
        print(f"Margin: {margin} USDT")
        print(f"Leverage: {leverage}x")
        print(f"Take Profit: {tp_price}")
        print(f"Stop Loss: {sl_price}")
        print("---------------------")

        confirm = input("Confirm order? (y/n): ")
        if confirm.lower() != 'y':
            print("Order cancelled.")
            exit()

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
    else:
        print(f"\nFailed to get current price for {symbol}")