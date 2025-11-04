import logging
import pandas as pd
import numpy as np
import time
import config

logger = logging.getLogger(__name__)

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
        # In debug mode, generate frequent alternating signals for the latest bar
        # This will ensure a signal is always present for the most recent data point
        if (len(df) - 1) % 2 == 0: # Alternate long and short signals on the latest bar
            df.at[len(df) - 1, 'LongSignal'] = True
            df.at[len(df) - 1, 'ShortSignal'] = False
        else:
            df.at[len(df) - 1, 'ShortSignal'] = True
            df.at[len(df) - 1, 'LongSignal'] = False
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
    logger.info(f"持倉: Bitmart={positions['bitmart']}, TopOne={positions['topone']}")

    # --- 決策方向 ---
    desired = None
    if long_signal and overall_trend != '空頭':
        desired = 'long'
    elif short_signal and overall_trend != '多頭':
        desired = 'short'

    if not desired:
        msg = "無新訊號" if any(positions.values()) else "無持倉與新訊號"
        return {**results, "status": "no_action", "message": msg}

    opposite = 'short' if desired == 'long' else 'long'

    # --- 檢查是否需平倉 ---
    def need_close(cur, new): return cur and cur.get('side') != new

    close_actions = {
        "bitmart": need_close(positions["bitmart"], desired),
        "topone": need_close(positions["topone"], opposite)
    }

    for name, need in close_actions.items():
        if need:
            client = bitmart_client if name == 'bitmart' else topone_client
            res = client.close_position(symbol)
            results[f"{name}_close"] = res
            logger.info(f"{name} 平倉結果: {res}")
    if any(close_actions.values()):
        time.sleep(10)

    # --- 開倉 ---
    price = df_15m['Close'].iloc[-1]
    bm_tp, bm_sl = prepare_order_params(desired, price, tp_pct, sl_pct)
    tp_tp, tp_sl = bm_sl, bm_tp  # 對沖

    orders = {}
    if not positions["bitmart"]:
        orders["bitmart_order"] = bitmart_client.place_order(symbol, desired, margin, leverage, tp_price=bm_tp, sl_price=bm_sl)
    if not positions["topone"]:
        orders["topone_order"] = topone_client.place_order(symbol, opposite, margin, leverage, tp_price=tp_tp, sl_price=tp_sl)

    results.update(orders)
    results["status"] = "completed"
    results["message"] = f"Bitmart開{desired}倉，TopOne開{opposite}倉對沖。"
    return results
