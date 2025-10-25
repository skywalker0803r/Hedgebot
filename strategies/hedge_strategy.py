import time
import streamlit as st 
from exchanges.bitmart_client import BitmartClient
from exchanges.topone_client import TopOneClient

def run_hedge_strategy(bitmart_client: BitmartClient, topone_client: TopOneClient, **kwargs):
    symbol = kwargs.get('symbol')
    bitmart_side = kwargs.get('bitmart_side')
    margin = kwargs.get('margin')
    leverage = kwargs.get('leverage')
    tp_percentage = kwargs.get('tp_percentage')
    sl_percentage = kwargs.get('sl_percentage')

    # Determine TopOne side
    topone_side = "short" if bitmart_side.lower() == "long" else "long"
    if bitmart_side.lower() not in ["long", "short"]:
        st.error(f"Invalid Bitmart side: {bitmart_side}. Must be 'long' or 'short'.")
        return

    # Get current price from Bitmart
    current_price = bitmart_client.get_current_price(symbol)
    if not current_price:
        st.error(f"Failed to get current price for {symbol} from Bitmart.")
        return

    st.write(f"Current price of {symbol} (from Bitmart) is {current_price}")

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

    st.subheader("Hedge Strategy Summary")
    st.write(f"Symbol: {symbol}")
    st.write(f"Bitmart Side: {bitmart_side}, TopOne Side: {topone_side}")
    st.write(f"Margin per exchange: {margin} USDT, Leverage: {leverage}x")
    st.write(f"Bitmart TP: {bitmart_tp_price:.4f}, SL: {bitmart_sl_price:.4f}")
    st.write(f"TopOne TP: {topone_tp_price:.4f}, SL: {topone_sl_price:.4f}")

    st.subheader("Opening Positions...")
    bitmart_order_response = bitmart_client.place_order(
        symbol=symbol,
        side=bitmart_side,
        margin=margin,
        leverage=leverage,
        tp_price=bitmart_tp_price,
        sl_price=bitmart_sl_price
    )
    if bitmart_order_response:
        st.success(f"Bitmart order placed successfully: {bitmart_order_response}")
    else:
        st.error("Failed to place Bitmart order.")

    topone_order_response = topone_client.place_order(
        symbol=symbol,
        side=topone_side,
        margin=margin,
        leverage=leverage,
        tp_price=topone_tp_price,
        sl_price=topone_sl_price
    )
    if topone_order_response:
        st.success(f"TopOne order placed successfully: {topone_order_response}")
    else:
        st.error("Failed to place TopOne order.")

    if not bitmart_order_response and not topone_order_response:
        st.warning("No orders were placed. Exiting strategy.")
    else:
        st.info("Holding positions for 1 minute...")
        time.sleep(60)

        st.subheader("Closing Positions...")
        bitmart_close_response = bitmart_client.close_position(symbol)
        if bitmart_close_response:
            st.success(f"Bitmart position closed successfully: {bitmart_close_response}")
        else:
            st.error("Failed to close Bitmart position.")

        topone_close_response = topone_client.close_position(symbol)
        if topone_close_response:
            st.success(f"TopOne position closed successfully: {topone_close_response}")
        else:
            st.error("Failed to close TopOne position.")

    st.subheader("Hedge Strategy Completed!")
