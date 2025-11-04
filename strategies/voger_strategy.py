import logging
import pandas as pd
import numpy as np
import time
import config
import random

logger = logging.getLogger(__name__)

# Global variables for debug signal sequence
_debug_signal_sequence_counter = 0
_debug_signal_sequence = ['none', 'long', 'none', 'none', 'short', 'none', 'none', 'long']

# ---------- CCI 指標 ----------
def cci(df, period=20):
    tp = (df['High'] + df['Low'] + df['Close']) / 3
    ma = tp.rolling(period).mean()
    md = tp.rolling(period).apply(lambda x: np.mean(np.abs(x - np.mean(x))), raw=True)
    return (tp - ma) / (0.015 * md + 1e-9)

# ---------- 產生交易訊號 ----------
def signal_generation(df, cci_len=20, lookback_bars=5, pullback_len=5, pullback_pct=0.01, debug_mode=False):
    df['CCI'] = cci(df, cci_len)
    df['TrendUp'] = df['CCI'] >= 0
    df['TrendUpPrev'] = df['TrendUp'].shift(1).astype(bool).fillna(False)
    df['PrevHigh'] = df['Close'].shift(1).rolling(lookback_bars).max()
    df['PrevLow'] = df['Close'].shift(1).rolling(lookback_bars).min()

    df['BullCross'] = (~df['TrendUpPrev']) & df['TrendUp'] & (df['Close'] > df['PrevHigh'])
    df['BearCross'] = df['TrendUpPrev'] & (~df['TrendUp']) & (df['Close'] < df['PrevLow'])
    df['LongSignal'], df['ShortSignal'] = False, False

    if debug_mode:
        global _debug_signal_sequence_counter
        global _debug_signal_sequence

        signal_choice = _debug_signal_sequence[_debug_signal_sequence_counter % len(_debug_signal_sequence)]
        _debug_signal_sequence_counter += 1

        latest_bar_index = len(df) - 1

        df.at[latest_bar_index, 'LongSignal'] = False
        df.at[latest_bar_index, 'ShortSignal'] = False

        if signal_choice == 'long':
            df.at[latest_bar_index, 'LongSignal'] = True
        elif signal_choice == 'short':
            df.at[latest_bar_index, 'ShortSignal'] = True

        logger.info(f"DEBUG MODE: Generated signal: {signal_choice}")
        return df

    bull_trigger = bear_trigger = None
    bull_count = bear_count = 0

    for i in range(len(df)):
        if df['BullCross'].iloc[i]:
            bull_trigger, bull_count = df['Close'].iloc[i] * (1 - pullback_pct), 0
        if bull_trigger:
            bull_count += 1
            if df['Low'].iloc[i] <= bull_trigger or bull_count >= pullback_len:
                df.at[i, 'LongSignal'], bull_trigger = True, None

        if df['BearCross'].iloc[i]:
            bear_trigger, bear_count = df['Close'].iloc[i] * (1 + pullback_pct), 0
        if bear_trigger:
            bear_count += 1
            if df['High'].iloc[i] >= bear_trigger or bear_count >= pullback_len:
                df.at[i, 'ShortSignal'], bear_trigger = True, None

    return df

# ---------- 多時間框架趨勢 ----------
def mtf_trend(df, cci_len=20):
    return '多頭' if cci(df, cci_len).iloc[-1] >= 0 else '空頭'

# ---------- 抽取共用函式 ----------
def load_kline_df(client, symbol, interval, bars):
    end = int(time.time())
    start = end - bars * interval * 60
    data = client.get_kline_data(symbol, interval, start, end)
    if not data: return None
    if isinstance(data[0], dict):
        data = [[k['timestamp'], k['open_price'], k['high_price'], k['low_price'], k['close_price'], k['volume']] for k in data]
    df = pd.DataFrame(data, columns=['timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
    df = df.apply(lambda x: pd.to_numeric(x, errors='coerce'))
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s', errors='coerce')
    return df.dropna()

def prepare_order_params(side, price, tp_pct, sl_pct):
    if side == 'long':
        return price * (1 + tp_pct/100), price * (1 - sl_pct/100)
    else:
        return price * (1 - tp_pct/100), price * (1 + sl_pct/100)

def get_position_summary(position):
    logger.debug(f"get_position_summary received position: {position}")
    if position is None:
        return "無持倉"
    
    # Check for TopOne's 'side' field
    side = position.get('side')
    if side == 'long':
        return "多頭"
    elif side == 'short':
        return "空頭"

    # Check for Bitmart's 'position_type' field
    position_type = position.get('position_type')
    if position_type == 1: # 1 for long
        return "多頭"
    elif position_type == 2: # 2 for short
        return "空頭"

    return "未知持倉"

# ---------- 策略主流程 ----------
def run_voger_strategy(bitmart_client, topone_client, **kwargs):
    symbol = kwargs['symbol']
    margin, leverage = kwargs['margin'], kwargs['leverage']
    tp_pct, sl_pct = kwargs['tp_percentage'], kwargs['sl_percentage']
    lookback_bars, pullback_pct = kwargs.get('lookback_bars', 5), kwargs.get('pullback_pct', 0.01)

    results = {"strategy": "Voger", "status": "pending", "message": ""}

    # --- 15分K線 ---
    df_15m = load_kline_df(bitmart_client, symbol, 15, 200)
    if df_15m is None or df_15m.empty:
        return {**results, "status": "failed", "message": f"{symbol} 無法取得15分K線"}

    df_15m = signal_generation(df_15m, lookback_bars=lookback_bars, pullback_pct=pullback_pct, debug_mode=config.DEBUG_MODE)
    latest = df_15m.iloc[-1]
    long_signal, short_signal = latest['LongSignal'], latest['ShortSignal']

    # --- 4小時趨勢 ---
    df_4h = load_kline_df(bitmart_client, symbol, 240, 60)
    overall_trend = mtf_trend(df_4h) if df_4h is not None and not df_4h.empty else '無資料'
    logger.info(f"4小時整體趨勢：{overall_trend}")

    # --- 取得持倉 ---
    positions = {
        "bitmart": bitmart_client.get_position(symbol),
        "topone": topone_client.get_position(symbol)
    }
    logger.info(f"持倉狀況: Bitmart={get_position_summary(positions['bitmart'])}, TopOne={get_position_summary(positions['topone'])}")

    # --- 決策方向 ---
    desired = None
    if config.DEBUG_MODE:
        if long_signal:
            desired = 'long'
        elif short_signal:
            desired = 'short'
    else: # Original logic
        if long_signal and overall_trend != '空頭':
            desired = 'long'
        elif short_signal and overall_trend != '多頭':
            desired = 'short'

    # Determine if any positions are currently open
    bitmart_has_position = positions["bitmart"] is not None
    topone_has_position = positions["topone"] is not None
    any_open_positions = bitmart_has_position or topone_has_position

    # Get current position summaries for comparison
    bitmart_pos_summary = get_position_summary(positions["bitmart"])
    topone_pos_summary = get_position_summary(positions["topone"])

    # Check if existing positions already form a valid hedge aligned with the desired signal
    should_skip_closing = False
    if desired == 'long' and bitmart_pos_summary == '多頭' and topone_pos_summary == '空頭':
        should_skip_closing = True
        logger.info("Existing positions already form a desired LONG hedge. Skipping closing.")
    elif desired == 'short' and bitmart_pos_summary == '空頭' and topone_pos_summary == '多頭':
        should_skip_closing = True
        logger.info("Existing positions already form a desired SHORT hedge. Skipping closing.")

    # If a signal is generated, and there are any open positions, close them all first.
    # This ensures "平倉一起平" (close together) unless already in desired hedged state.
    if desired is not None and any_open_positions and not should_skip_closing:
        logger.info("Signal detected and open positions exist, but not in desired hedged state. Attempting to close all positions first.")
        if bitmart_has_position:
            bitmart_client.close_position(symbol)
            logger.info("Bitmart position closed.")
        if topone_has_position:
            topone_client.close_position(symbol)
            logger.info("TopOne position closed.")
        time.sleep(5) # Wait for positions to close

        # After closing, re-fetch positions to ensure they are indeed closed
        positions["bitmart"] = bitmart_client.get_position(symbol)
        positions["topone"] = topone_client.get_position(symbol)
        bitmart_has_position = positions["bitmart"] is not None
        topone_has_position = positions["topone"] is not None
        any_open_positions = bitmart_has_position or topone_has_position

        if any_open_positions:
            logger.warning("Failed to close all positions. Aborting current cycle.")
            return {**results, "status": "failed_to_close", "message": "未能平倉所有部位"}


    # If no signal, or if all positions were just closed and no new signal to open
    if not desired:
        msg = "無新訊號" if any_open_positions else "無持倉與新訊號"
        return {**results, "status": "no_action", "message": msg}

    opposite = 'short' if desired == 'long' else 'long'

    # --- 開倉 ---
    # This ensures "開倉一起開" (open together)
    # Only attempt to open if no positions are currently open after potential closing
    if not bitmart_has_position and not topone_has_position:
        price = df_15m['Close'].iloc[-1]
        bm_tp, bm_sl = prepare_order_params(desired, price, tp_pct, sl_pct)
        tp_tp, tp_sl = bm_sl, bm_tp  # 對沖

        orders = {}
        bitmart_order_res = bitmart_client.place_order(symbol, desired, margin, leverage, tp_price=bm_tp, sl_price=bm_sl)
        topone_order_res = topone_client.place_order(symbol, opposite, margin, leverage, tp_price=tp_tp, sl_price=tp_sl)

        if bitmart_order_res and topone_order_res:
            orders["bitmart_order"] = bitmart_order_res
            orders["topone_order"] = topone_order_res
            results.update(orders)
            results["status"] = "completed"
            results["message"] = f"Bitmart開{desired}倉，TopOne開{opposite}倉對沖。"
        else:
            results["status"] = "failed_to_open"
            results["message"] = "未能同時開倉"
            # If one failed, consider closing the other if it opened
            if bitmart_order_res and not topone_order_res:
                logger.warning("Bitmart opened, but TopOne failed. Attempting to close Bitmart position.")
                bitmart_client.close_position(symbol)
            elif topone_order_res and not bitmart_order_res:
                logger.warning("TopOne opened, but Bitmart failed. Attempting to close TopOne position.")
                topone_client.close_position(symbol)
    else:
        results["status"] = "no_action"
        results["message"] = "已有部位，不重複開倉"


    return results
