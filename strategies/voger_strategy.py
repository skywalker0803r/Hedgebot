import logging
import pandas as pd
import numpy as np
import time
from exchanges.bitmart_client import BitmartClient
from exchanges.topone_client import TopOneClient

logger = logging.getLogger(__name__)

# ... (cci, signal_generation, mtf_panel functions remain the same) ...

# ---------- CCI Calculation ----------
def cci(df, period=20):
    tp = (df['High'] + df['Low'] + df['Close']) / 3
    ma = tp.rolling(period).mean()
    md = tp.rolling(period).apply(lambda x: np.mean(np.abs(x - np.mean(x))), raw=True)
    # Add a small epsilon to avoid division by zero
    return (tp - ma) / (0.015 * md + 1e-9)

# ---------- Signal Generation ----------
def signal_generation(df, cci_len=20, lookback_bars=5, pullback_len=5, pullback_pct=0.01):
    df['CCI'] = cci(df, cci_len)
    df['TrendUp'] = (df['CCI'] >= 0).astype(bool)
    df['TrendUpPrev'] = df['TrendUp'].shift(1).fillna(False).astype(bool)

    df['PrevHigh'] = df['Close'].shift(1).rolling(lookback_bars).max()
    df['PrevLow']  = df['Close'].shift(1).rolling(lookback_bars).min()

    df['BullCross'] = (~df['TrendUpPrev']) & df['TrendUp'] & (df['Close'] > df['PrevHigh'])
    df['BearCross'] = df['TrendUpPrev'] & (~df['TrendUp']) & (df['Close'] < df['PrevLow'])

    df['LongSignal'] = False
    df['ShortSignal'] = False

    bull_trigger = None
    bull_count = 0
    bear_trigger = None
    bear_count = 0

    for i in range(len(df)):
        if df['BullCross'].iloc[i]:
            bull_trigger = df['Close'].iloc[i] * (1 - pullback_pct)
            bull_count = 0
        if bull_trigger is not None:
            bull_count += 1
            if df['Low'].iloc[i] <= bull_trigger or bull_count >= pullback_len:
                df.at[i, 'LongSignal'] = True
                bull_trigger = None
                bull_count = 0

        if df['BearCross'].iloc[i]:
            bear_trigger = df['Close'].iloc[i] * (1 + pullback_pct)
            bear_count = 0
        if bear_trigger is not None:
            bear_count += 1
            if df['High'].iloc[i] >= bear_trigger or bear_count >= pullback_len:
                df.at[i, 'ShortSignal'] = True
                bear_trigger = None
                bear_count = 0
    return df

# ---------- Multi-Timeframe Panel ----------
def mtf_panel(df_dict, cci_len=20):
    panel = {}
    for tf, df in df_dict.items():
        if df is not None and not df.empty:
            cci_val = cci(df, cci_len)
            panel[tf] = 'Bull' if cci_val.iloc[-1] >= 0 else 'Bear'
        else:
            panel[tf] = 'N/A'
    return panel

def run_voger_strategy(bitmart_client: BitmartClient, topone_client: TopOneClient, **kwargs):
    logger.info("Running Voger Strategy with Position Management...")

    symbol = kwargs.get('symbol')
    margin = kwargs.get('margin')
    leverage = kwargs.get('leverage')
    tp_percentage = kwargs.get('tp_percentage')
    sl_percentage = kwargs.get('sl_percentage')

    results = {
        "strategy": "Voger", "status": "pending", "message": "",
        "bitmart_order": None, "topone_order": None,
        "bitmart_close": None, "topone_close": None,
    }

    # 1. Fetch Data and Generate Signals
    end_time = int(time.time())
    start_time = end_time - 200 * 15 * 60
    kline_data = bitmart_client.get_kline_data(symbol, 15, start_time, end_time)

    if not kline_data:
        results.update({"message": f"Failed to fetch 15m k-line data for {symbol}.", "status": "failed"})
        logger.error(results["message"])
        return results

    # Process K-line data (handle both list of dicts and list of lists)
    if isinstance(kline_data[0], dict):
        processed_data = []
        for kline in kline_data:
            processed_data.append([
                kline.get('timestamp'),
                kline.get('open_price'),
                kline.get('high_price'),
                kline.get('low_price'),
                kline.get('close_price'),
                kline.get('volume')
            ])
        df_15m = pd.DataFrame(processed_data, columns=['timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
    else:
        df_15m = pd.DataFrame(kline_data, columns=['timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])

    # Convert data types
    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
        df_15m[col] = pd.to_numeric(df_15m[col], errors='coerce')
    df_15m['timestamp'] = pd.to_datetime(df_15m['timestamp'], unit='s', errors='coerce')
    df_15m.dropna(inplace=True)

    if df_15m.empty:
        results.update({"message": f"K-line data for {symbol} was empty or could not be processed.", "status": "failed"})
        logger.error(results["message"])
        return results

    df_15m = signal_generation(df_15m.copy())
    latest_signal = df_15m.iloc[-1]
    long_signal = latest_signal['LongSignal']
    short_signal = latest_signal['ShortSignal']

    # 2. Check Current Positions
    bitmart_pos = bitmart_client.get_position(symbol)
    topone_pos = topone_client.get_position(symbol)
    current_bitmart_side = bitmart_pos.get('side') if bitmart_pos else None
    current_topone_side = topone_pos.get('side') if topone_pos else None
    logger.info(f"Current positions: Bitmart={current_bitmart_side}, TopOne={current_topone_side}")

    # 3. Decision Logic
    desired_bitmart_side = None
    if long_signal:
        desired_bitmart_side = 'long'
    elif short_signal:
        desired_bitmart_side = 'short'

    # Determine if we need to close, open, or do nothing
    need_to_close = False
    if current_bitmart_side and desired_bitmart_side and current_bitmart_side != desired_bitmart_side:
        need_to_close = True
        logger.info(f"Signal changed. Current: {current_bitmart_side}, New: {desired_bitmart_side}. Closing positions.")

    need_to_open = False
    if desired_bitmart_side and not current_bitmart_side:
        need_to_open = True
        logger.info(f"No current position and new signal detected: {desired_bitmart_side}. Opening positions.")

    # 4. Execute Actions
    if need_to_close:
        bm_close = bitmart_client.close_position(symbol)
        tp_close = topone_client.close_position(symbol)
        results.update({"bitmart_close": bm_close, "topone_close": tp_close, "message": "Closed positions due to signal change."})
        logger.info(f"Closing results: Bitmart={bm_close}, TopOne={tp_close}")
        time.sleep(2) # Wait for positions to close

    if need_to_open:
        topone_side = "short" if desired_bitmart_side == "long" else "long"
        current_price = df_15m['Close'].iloc[-1]
        
        # Calculate TP/SL
        if desired_bitmart_side == 'long':
            bm_tp = current_price * (1 + tp_percentage / 100)
            bm_sl = current_price * (1 - sl_percentage / 100)
            tp_tp = bm_sl
            tp_sl = bm_tp
        else:
            bm_tp = current_price * (1 - tp_percentage / 100)
            bm_sl = current_price * (1 + sl_percentage / 100)
            tp_tp = bm_sl
            tp_sl = bm_tp

        logger.info(f"Placing orders: Bitmart={desired_bitmart_side}, TopOne={topone_side}")
        bm_order = bitmart_client.place_order(symbol, desired_bitmart_side, margin, leverage, tp_price=bm_tp, sl_price=bm_sl)
        tp_order = topone_client.place_order(symbol, topone_side, margin, leverage, tp_price=tp_tp, sl_price=tp_sl)
        results.update({"bitmart_order": bm_order, "topone_order": tp_order, "status": "completed", "message": f"Opened {desired_bitmart_side} hedge."})
    
    elif not need_to_close and not need_to_open:
        if current_bitmart_side:
            results.update({"status": "holding", "message": f"Holding existing {current_bitmart_side} position. No new signal."})
            logger.info(results["message"])
        else:
            results.update({"status": "no_action", "message": "No position and no new signal."})
            logger.info(results["message"])

    return results
