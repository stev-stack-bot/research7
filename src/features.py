import numpy as np
import pandas as pd

def compute_ofi_delta(prev_levels, curr_levels, levels_count=5):
    """
    Calculate Order Flow Imbalance (OFI) delta between two book states.
    prev_levels, curr_levels are lists of dicts: [{'px': str, 'sz': str, 'n': int}, ...]
    bids are index 0, asks are index 1.
    """
    # Initialize bid and ask flows
    bid_flow = 0.0
    ask_flow = 0.0
    
    prev_bids = prev_levels[0]
    prev_asks = prev_levels[1]
    curr_bids = curr_levels[0]
    curr_asks = curr_levels[1]
    
    # Calculate bid flows up to levels_count
    for i in range(min(levels_count, len(prev_bids), len(curr_bids))):
        p_prev = float(prev_bids[i]["px"])
        v_prev = float(prev_bids[i]["sz"])
        p_curr = float(curr_bids[i]["px"])
        v_curr = float(curr_bids[i]["sz"])
        
        if p_curr > p_prev:
            bid_flow += v_curr
        elif p_curr == p_prev:
            bid_flow += (v_curr - v_prev)
        else:
            bid_flow += (-v_prev)
            
    # Calculate ask flows up to levels_count
    for i in range(min(levels_count, len(prev_asks), len(curr_asks))):
        p_prev = float(prev_asks[i]["px"])
        v_prev = float(prev_asks[i]["sz"])
        p_curr = float(curr_asks[i]["px"])
        v_curr = float(curr_asks[i]["sz"])
        
        if p_curr < p_prev:
            ask_flow += v_curr
        elif p_curr == p_prev:
            ask_flow += (v_curr - v_prev)
        else:
            ask_flow += (-v_prev)
            
    return bid_flow - ask_flow

def compute_bar_features(bars_df, book_bar_mapping, levels_count=5, z_window=100):
    """
    Compute cumulative OFI for each bar and build features.
    """
    # Group book updates by bar index
    bar_to_books = {}
    for bar_idx, book_row in book_bar_mapping:
        if bar_idx not in bar_to_books:
            bar_to_books[bar_idx] = []
        bar_to_books[bar_idx].append(book_row)
        
    cofi_values = []
    
    for idx, row in bars_df.iterrows():
        bar_idx = row["bar_index"]
        bar_books = bar_to_books.get(bar_idx, [])
        
        if not bar_books:
            cofi_values.append(0.0)
            continue
            
        bar_ofi = 0.0
        prev_levels = bar_books[0]["levels"]
        
        for k in range(1, len(bar_books)):
            curr_levels = bar_books[k]["levels"]
            bar_ofi += compute_ofi_delta(prev_levels, curr_levels, levels_count)
            prev_levels = curr_levels
            
        cofi_values.append(bar_ofi)
        
    bars_df["cofi"] = cofi_values
    
    # Calculate rolling z-score of COFI
    rolling_mean = bars_df["cofi"].rolling(window=z_window, min_periods=1).mean()
    rolling_std = bars_df["cofi"].rolling(window=z_window, min_periods=1).std().fillna(1.0)
    bars_df["cofi_z"] = (bars_df["cofi"] - rolling_mean) / rolling_std
    
    # Calculate rolling volatility of returns over 100 bars
    # Return of bar k is ln(close_k / close_{k-1})
    bars_df["ret"] = np.log(bars_df["close"] / bars_df["close"].shift(1)).fillna(0.0)
    bars_df["volatility"] = bars_df["ret"].rolling(window=100, min_periods=1).std().fillna(0.0001)
    
    # Lagged features for secondary meta-labeling model
    bars_df["volatility_ratio"] = (
        bars_df["ret"].rolling(window=10, min_periods=1).std() / 
        bars_df["volatility"]
    ).fillna(1.0)
    
    # Bar duration in seconds
    bars_df["duration"] = (bars_df["end_time"] - bars_df["start_time"]) / 1000.0
    
    # Depth imbalance at level 1 (bid size / ask size)
    depth_ratio = []
    for idx, row in bars_df.iterrows():
        bar_idx = row["bar_index"]
        bar_books = bar_to_books.get(bar_idx, [])
        if bar_books:
            last_book = bar_books[-1]
            try:
                bid_sz = float(last_book["levels"][0][0]["sz"])
                ask_sz = float(last_book["levels"][1][0]["sz"])
                depth_ratio.append(bid_sz / ask_sz if ask_sz > 0 else 1.0)
            except Exception:
                depth_ratio.append(1.0)
        else:
            depth_ratio.append(1.0)
            
    bars_df["depth_ratio"] = depth_ratio
    
    # Add next-bar returns as prediction target (non-leaked, target is shift(-1))
    bars_df["next_ret"] = bars_df["ret"].shift(-1)
    
    # Extract bid/ask prices at the close of the bar
    bid_prices = []
    ask_prices = []
    for idx, row in bars_df.iterrows():
        bar_idx = row["bar_index"]
        bar_books = bar_to_books.get(bar_idx, [])
        if bar_books:
            last_book = bar_books[-1]
            try:
                bid_px = float(last_book["levels"][0][0]["px"])
                ask_px = float(last_book["levels"][1][0]["px"])
                bid_prices.append(bid_px)
                ask_prices.append(ask_px)
            except Exception:
                bid_prices.append(row["close"])
                ask_prices.append(row["close"])
        else:
            bid_prices.append(row["close"])
            ask_prices.append(row["close"])
            
    bars_df["bid"] = bid_prices
    bars_df["ask"] = ask_prices
    
    return bars_df
