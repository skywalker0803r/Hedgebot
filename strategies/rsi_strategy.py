import pandas as pd
import ta
from datetime import datetime, timedelta
import time
import logging

from exchanges.bitmart_client import BitmartClient
from exchanges.topone_client import TopOneClient

logger = logging.getLogger(__name__)

def run_rsi_strategy(bitmart_client: BitmartClient, topone_client: TopOneClient, **kwargs):
    logger.info("Running RSI Strategy...")

    symbol = kwargs.get('symbol')
    margin = kwargs.get('margin')
    leverage = kwargs.get('leverage')
    tp_percentage = kwargs.get('tp_percentage')
    sl_percentage = kwargs.get('sl_percentage')

    results = {
        "strategy": "RSI",
        "status": "failed",
        "message": "",
        "bitmart_order": None,
        "topone_order": None,
        "bitmart_close": None,
        "topone_close": None,
    }

    # --- Configuration for RSI ---
    RSI_PERIOD = 14
    RSI_OVERBOUGHT = 60
    RSI_OVERSOLD = 40
    KLINE_INTERVAL = 1 # 1 minute klines
    KLINE_LIMIT = 100 # Fetch last 100 klines (need enough for RSI_PERIOD)

    # --- Fetch K-line data from Bitmart ---
    logger.info(f"Fetching {KLINE_LIMIT} {KLINE_INTERVAL}-minute K-lines for {symbol} from Bitmart...")
    end_time = int(time.time())
    start_time = int(end_time - (KLINE_LIMIT * KLINE_INTERVAL * 60)) # KLINE_LIMIT minutes ago

    kline_data = bitmart_client.get_kline_data(symbol, KLINE_INTERVAL, start_time, end_time)

    if not kline_data:
        logger.error("Failed to fetch K-line data or K-line data is empty. Cannot run RSI strategy.")
        results["message"] = "Failed to fetch K-line data."
        return results

    # --- Process K-line data ---
    logger.info(f"Raw K-line data sample: {kline_data[:2] if kline_data else 'No data'}")
    
    # Check if data is in dictionary format (Bitmart API format)
    if kline_data and isinstance(kline_data[0], dict):
        logger.info("K-line data is in dictionary format, converting...")
        
        # Convert dictionary format to DataFrame
        processed_data = []
        for kline in kline_data:
            processed_data.append([
                kline.get('timestamp', 0) * 1000,  # Convert to milliseconds
                kline.get('open_price', '0'),
                kline.get('high_price', '0'),
                kline.get('low_price', '0'),
                kline.get('close_price', '0'),
                kline.get('volume', '0')
            ])
        
        df = pd.DataFrame(processed_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        logger.info(f"Converted {len(processed_data)} dictionary records to DataFrame")
        
    else:
        # Original array format
        logger.info("K-line data is in array format")
        df = pd.DataFrame(kline_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    
    # Debug: Check raw data after initial processing
    logger.info(f"Raw close prices before conversion: {df['close'].head().tolist()}")
    
    # Convert data types with error handling
    df['close'] = pd.to_numeric(df['close'], errors='coerce')
    df['open'] = pd.to_numeric(df['open'], errors='coerce')
    df['high'] = pd.to_numeric(df['high'], errors='coerce')
    df['low'] = pd.to_numeric(df['low'], errors='coerce')
    df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', errors='coerce')
    
    # Check for conversion issues
    nan_close_count = df['close'].isna().sum()
    if nan_close_count > 0:
        logger.error(f"Found {nan_close_count} NaN values in close prices after conversion!")
        logger.error(f"Sample converted close values: {df['close'].head().tolist()}")
        results["message"] = "K-line data conversion failed - invalid price data format."
        return results
    
    # Drop any rows with NaN timestamps
    initial_len = len(df)
    df = df.dropna(subset=['timestamp', 'close'])
    if len(df) < initial_len:
        logger.warning(f"Dropped {initial_len - len(df)} rows due to invalid timestamps or prices")
    
    logger.info(f"Successfully processed {len(df)} K-line records")

    # --- Calculate RSI ---
    logger.info("Calculating RSI indicator...")
    
    # Debug: Log some data info
    logger.info(f"K-line data: {len(df)} bars")
    logger.info(f"Price range: {df['close'].min():.2f} - {df['close'].max():.2f}")
    logger.info(f"Latest prices: {df['close'].tail(5).tolist()}")
    
    # Calculate RSI with proper handling
    df['rsi'] = ta.momentum.rsi(df['close'], window=RSI_PERIOD, fillna=False)

    # Ensure we have enough data for RSI calculation
    if len(df) < RSI_PERIOD:
        logger.warning("Not enough K-line data to calculate RSI. Please increase KLINE_LIMIT.")
        results["message"] = "Not enough K-line data for RSI."
        return results

    # Check for valid RSI value
    last_rsi = df['rsi'].iloc[-1]
    
    # Validate RSI value
    if pd.isna(last_rsi):
        logger.error("RSI calculation resulted in NaN. Checking recent RSI values...")
        # Try to get the last valid RSI value
        valid_rsi_values = df['rsi'].dropna()
        if len(valid_rsi_values) > 0:
            last_rsi = valid_rsi_values.iloc[-1]
            logger.info(f"Using last valid RSI: {last_rsi:.2f}")
        else:
            logger.error("No valid RSI values found. Cannot proceed.")
            results["message"] = "No valid RSI values calculated."
            return results
    
    # Additional validation for extreme values
    if last_rsi < 0 or last_rsi > 100:
        logger.error(f"RSI value out of range: {last_rsi:.2f}. This indicates a calculation error.")
        # Log recent RSI values for debugging
        recent_rsi = df['rsi'].tail(10).dropna()
        logger.info(f"Recent RSI values: {recent_rsi.tolist()}")
        results["message"] = f"Invalid RSI value: {last_rsi:.2f}"
        return results
    
    logger.info(f"Last RSI: {last_rsi:.2f}")
    
    # Log additional RSI info for debugging
    rsi_stats = df['rsi'].describe()
    logger.info(f"RSI stats - Min: {rsi_stats['min']:.2f}, Max: {rsi_stats['max']:.2f}, Mean: {rsi_stats['mean']:.2f}")

    # --- Check current positions first ---
    logger.info("Fetching current positions...")
    bitmart_position = bitmart_client.get_position(symbol)
    topone_position = topone_client.get_position(symbol)
    logger.info(f"Raw Bitmart position: {bitmart_position}")
    logger.info(f"Raw TopOne position: {topone_position}")
    
    # Determine current position state
    current_bitmart_side = None
    current_topone_side = None
    
    # Check Bitmart position
    if bitmart_position:
        try:
            # Bitmart returns position data with various fields
            current_amount = float(bitmart_position.get('current_amount', 0))
            position_type = bitmart_position.get('position_type', 0)
            
            # Get contract size to convert contract count to actual size
            try:
                details_data = bitmart_client.futuresAPI.get_details(symbol)[0]['data']
                symbol_details = details_data['symbols'][0]
                contract_size = float(symbol_details['contract_size'])
                
                # Convert contract amount to actual position size
                actual_position_size = current_amount * contract_size
                
                logger.info(f"Bitmart position details:")
                logger.info(f"  Contract amount: {current_amount}")
                logger.info(f"  Contract size: {contract_size}")
                logger.info(f"  Actual position size: {actual_position_size}")
                
            except Exception as e:
                logger.warning(f"Could not get contract details for size conversion: {e}")
                actual_position_size = current_amount
            
            if current_amount > 0:
                if position_type == 1:  # Long position
                    current_bitmart_side = "long"
                elif position_type == 2:  # Short position
                    current_bitmart_side = "short"
                logger.info(f"Current Bitmart position: {current_bitmart_side} with {current_amount} contracts ({actual_position_size:.4f} actual size)")
        except (ValueError, TypeError) as e:
            logger.warning(f"Error parsing Bitmart position: {e}")
    
    # Check TopOne position  
    if topone_position:
        try:
            size = float(topone_position.get('size', 0))
            side = topone_position.get('side', '')
            
            if size > 0:
                current_topone_side = side.lower()  # 'long' or 'short'
                logger.info(f"Current TopOne position: {current_topone_side} with size {size}")
        except (ValueError, TypeError) as e:
            logger.warning(f"Error parsing TopOne position: {e}")
    
    if not current_bitmart_side:
        logger.info("No current Bitmart position found.")
    if not current_topone_side:
        logger.info("No current TopOne position found.")
    logger.info(f"Determined current_bitmart_side: {current_bitmart_side}, current_topone_side: {current_topone_side}")

    # --- Determine trading signal ---
    signal = None
    if last_rsi < RSI_OVERSOLD:
        signal = "oversold" # Buy signal
        logger.info(f"RSI ({last_rsi:.2f}) is below {RSI_OVERSOLD}! Oversold signal detected.")
    elif last_rsi > RSI_OVERBOUGHT:
        signal = "overbought" # Sell signal
        logger.info(f"RSI ({last_rsi:.2f}) is above {RSI_OVERBOUGHT}! Overbought signal detected.")
    else:
        logger.info(f"RSI ({last_rsi:.2f}) is within normal range ({RSI_OVERSOLD}-{RSI_OVERBOUGHT}). No action taken.")
        results["status"] = "no_signal"
        results["message"] = "RSI is within normal range."
        return results

    # --- Check if we need to take action ---
    need_to_close = False
    need_to_open = False
    
    if signal == "oversold":
        # We want: Bitmart LONG + TopOne SHORT
        if current_bitmart_side == "short" or current_topone_side == "long":
            need_to_close = True  # Wrong direction positions exist
        if current_bitmart_side != "long" or current_topone_side != "short":
            need_to_open = True   # Don't have the right positions
            
    elif signal == "overbought":
        # We want: Bitmart SHORT + TopOne LONG  
        if current_bitmart_side == "long" or current_topone_side == "short":
            need_to_close = True  # Wrong direction positions exist
        if current_bitmart_side != "short" or current_topone_side != "long":
            need_to_open = True   # Don't have the right positions

    logger.info(f"need_to_close: {need_to_close}, need_to_open: {need_to_open}")
    # If we already have the correct positions, no need to do anything
    if not need_to_close and not need_to_open:
        logger.info("✅ Already have correct positions for current RSI signal. No action needed.")
        results["status"] = "already_positioned"
        results["message"] = "Already have correct positions for current RSI signal."
        return results

    # --- Close positions only if needed ---
    if need_to_close:
        logger.info("🔄 Closing existing positions due to signal change...")
        
        bitmart_close_response = bitmart_client.close_position(symbol)
        if bitmart_close_response:
            logger.info(f"Closed existing Bitmart position: {bitmart_close_response}")
            results["bitmart_close"] = bitmart_close_response
        else:
            logger.info("No existing Bitmart position to close or close failed.")

        topone_close_response = topone_client.close_position(symbol)
        if topone_close_response:
            logger.info(f"Closed existing TopOne position: {topone_close_response}")
            results["topone_close"] = topone_close_response
        else:
            logger.info("No existing TopOne position to close or close failed.")

        # Wait for positions to close
        time.sleep(2)
    
    # --- Open positions only if needed ---
    if not need_to_open:
        logger.info("✅ No need to open new positions.")
        results["status"] = "closed_only"
        results["message"] = "Closed wrong direction positions only."
        return results

    # --- Execute trades based on signal (copied from hedge_strategy.py) ---
    # Get current price from Bitmart (same as hedge strategy)
    current_price = bitmart_client.get_current_price(symbol)
    if not current_price:
        logger.error(f"Failed to get current price for {symbol} from Bitmart.")
        results["message"] = f"Failed to get current price for {symbol} from Bitmart."
        return results

    logger.info(f"Current price of {symbol} (from Bitmart) is {current_price}")

    if signal == "oversold":
        # RSI < 20: Open long on Bitmart, short on TopOne
        bitmart_side = "long"
        topone_side = "short"
        
        # Calculate TP/SL for Bitmart (same logic as hedge strategy)
        bitmart_tp_price = current_price * (1 + tp_percentage / 100)
        bitmart_sl_price = current_price * (1 - sl_percentage / 100)
        
        # Calculate TP/SL for TopOne (opposite side)
        topone_tp_price = bitmart_sl_price #current_price * (1 - tp_percentage / 100)
        topone_sl_price = bitmart_tp_price #current_price * (1 + sl_percentage / 100)

        logger.info("--- RSI Oversold Signal ---")
        logger.info(f"Symbol: {symbol}")
        logger.info(f"Bitmart Side: {bitmart_side}, TopOne Side: {topone_side}")
        logger.info(f"Margin per exchange: {margin} USDT, Leverage: {leverage}x")
        logger.info(f"Bitmart TP: {bitmart_tp_price:.4f}, SL: {bitmart_sl_price:.4f}")
        logger.info(f"TopOne TP: {topone_tp_price:.4f}, SL: {topone_sl_price:.4f}")

    elif signal == "overbought":
        # RSI > 80: Open short on Bitmart, long on TopOne
        bitmart_side = "short"
        topone_side = "long"
        
        # Calculate TP/SL for Bitmart (same logic as hedge strategy)
        bitmart_tp_price = current_price * (1 - tp_percentage / 100)
        bitmart_sl_price = current_price * (1 + sl_percentage / 100)
        
        # Calculate TP/SL for TopOne (opposite side)
        topone_tp_price = bitmart_sl_price #current_price * (1 - tp_percentage / 100)
        topone_sl_price = bitmart_tp_price #current_price * (1 + sl_percentage / 100)

        logger.info("--- RSI Overbought Signal ---")
        logger.info(f"Symbol: {symbol}")
        logger.info(f"Bitmart Side: {bitmart_side}, TopOne Side: {topone_side}")
        logger.info(f"Margin per exchange: {margin} USDT, Leverage: {leverage}x")
        logger.info(f"Bitmart TP: {bitmart_tp_price:.4f}, SL: {bitmart_sl_price:.4f}")
        logger.info(f"TopOne TP: {topone_tp_price:.4f}, SL: {topone_sl_price:.4f}")

    # Place orders using exact same method as hedge strategy
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

    results["status"] = "completed"
    results["message"] = "RSI strategy execution completed."
    logger.info("RSI Strategy Execution Completed!")
    return results
