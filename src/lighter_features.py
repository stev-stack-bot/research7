import numpy as np
import pandas as pd
from bisect import bisect_left

def compute_ofi_delta(prev_levels, curr_levels, levels_count=5):
    """
    Calculate Order Flow Imbalance (OFI) delta between two book states.
    prev_levels, curr_levels are lists of lists: [bids, asks]
    where bids/asks are lists of dicts: [{'px': float, 'sz': float}]
    """
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

def compute_lighter_bar_features(bars_df, book_bar_mapping, trade_events, levels_count=5, z_window=100):
    """
    Compute cumulative OFI for each bar and build features.
    """
    # Group book updates by bar index
    bar_to_books = {}
    for bar_idx, book_row in book_bar_mapping:
        if bar_idx not in bar_to_books:
            bar_to_books[bar_idx] = []
        bar_to_books[bar_idx].append(book_row)
        
    # Get sorted book updates across all mapping
    all_books = sorted([row for _, row in book_bar_mapping], key=lambda x: x["time"])
    book_times = [b["time"] for b in all_books]
    
    cofi_values = []
    cofi_l1_values = []
    avg_spread_values = []
    micro_prices = []
    depth_ratio_l3 = []
    depth_ratio_l5 = []
    
    # Track rolling states for fallback
    last_p_micro = None
    last_spread = 0.0
    
    for idx, row in bars_df.iterrows():
        bar_idx = row["bar_index"]
        bar_books = bar_to_books.get(bar_idx, [])
        
        if not bar_books:
            cofi_values.append(0.0)
            cofi_l1_values.append(0.0)
            avg_spread_values.append(last_spread)
            micro_prices.append(last_p_micro if last_p_micro is not None else row["close"])
            depth_ratio_l3.append(1.0)
            depth_ratio_l5.append(1.0)
            continue
            
        # Calculate OFI
        bar_ofi = 0.0
        bar_ofi_l1 = 0.0
        prev_levels = bar_books[0]["levels"]
        
        spreads = []
        for k in range(len(bar_books)):
            curr_levels = bar_books[k]["levels"]
            if k > 0:
                bar_ofi += compute_ofi_delta(prev_levels, curr_levels, levels_count)
                bar_ofi_l1 += compute_ofi_delta(prev_levels, curr_levels, levels_count=1)
                prev_levels = curr_levels
            
            # Calculate spread
            if len(curr_levels[0]) > 0 and len(curr_levels[1]) > 0:
                spreads.append(float(curr_levels[1][0]["px"]) - float(curr_levels[0][0]["px"]))
                
        cofi_values.append(bar_ofi)
        cofi_l1_values.append(bar_ofi_l1)
        
        if spreads:
            last_spread = np.mean(spreads)
        avg_spread_values.append(last_spread)
        
        # Micro-price calculation (using last book update of the bar)
        last_book = bar_books[-1]
        try:
            bid_px = float(last_book["levels"][0][0]["px"])
            bid_sz = float(last_book["levels"][0][0]["sz"])
            ask_px = float(last_book["levels"][1][0]["px"])
            ask_sz = float(last_book["levels"][1][0]["sz"])
            
            if bid_sz + ask_sz > 0:
                last_p_micro = (bid_px * ask_sz + ask_px * bid_sz) / (bid_sz + ask_sz)
            else:
                last_p_micro = row["close"]
        except Exception:
            last_p_micro = row["close"]
            
        micro_prices.append(last_p_micro)
        
        # Depth ratios (L3, L5)
        try:
            bids_l3 = sum(float(b["sz"]) for b in last_book["levels"][0][:3])
            asks_l3 = sum(float(a["sz"]) for a in last_book["levels"][1][:3])
            depth_ratio_l3.append(bids_l3 / asks_l3 if asks_l3 > 0 else 1.0)
        except Exception:
            depth_ratio_l3.append(1.0)
            
        try:
            bids_l5 = sum(float(b["sz"]) for b in last_book["levels"][0][:5])
            asks_l5 = sum(float(a["sz"]) for a in last_book["levels"][1][:5])
            depth_ratio_l5.append(bids_l5 / asks_l5 if asks_l5 > 0 else 1.0)
        except Exception:
            depth_ratio_l5.append(1.0)
            
    # Assign features
    bars_df["cofi"] = cofi_values
    bars_df["cofi_l1"] = cofi_l1_values
    bars_df["avg_spread"] = avg_spread_values
    bars_df["micro_price"] = micro_prices
    bars_df["depth_ratio_l3"] = depth_ratio_l3
    bars_df["depth_ratio_l5"] = depth_ratio_l5
    
    # Calculate rolling z-scores
    rolling_mean = bars_df["cofi"].rolling(window=z_window, min_periods=1).mean()
    rolling_std = bars_df["cofi"].rolling(window=z_window, min_periods=1).std().fillna(1.0)
    bars_df["cofi_z"] = (bars_df["cofi"] - rolling_mean) / rolling_std
    
    rolling_mean_l1 = bars_df["cofi_l1"].rolling(window=z_window, min_periods=1).mean()
    rolling_std_l1 = bars_df["cofi_l1"].rolling(window=z_window, min_periods=1).std().fillna(1.0)
    bars_df["cofi_l1_z"] = (bars_df["cofi_l1"] - rolling_mean_l1) / rolling_std_l1
    
    # Returns and micro-returns
    bars_df["ret"] = np.log(bars_df["close"] / bars_df["close"].shift(1)).fillna(0.0)
    bars_df["micro_ret"] = np.log(bars_df["micro_price"] / bars_df["micro_price"].shift(1)).fillna(0.0)
    
    # Volatility
    bars_df["volatility"] = bars_df["ret"].rolling(window=z_window, min_periods=1).std().fillna(0.0001)
    bars_df["volatility_ratio"] = (
        bars_df["ret"].rolling(window=10, min_periods=1).std() / 
        bars_df["volatility"]
    ).fillna(1.0)
    
    # Bar duration
    bars_df["duration"] = (bars_df["end_time"] - bars_df["start_time"]) / 1000000.0
    
    # Momentum (Lagged Returns)
    bars_df["ret_lag1"] = bars_df["ret"].shift(1).fillna(0.0)
    bars_df["ret_lag2"] = bars_df["ret"].shift(2).fillna(0.0)
    
    # Compute VPIN for each bar
    vpin_values = []
    for idx, row in bars_df.iterrows():
        t_start = row["start_time"]
        t_end = row["end_time"]
        
        # Filter trades in this bar
        bar_trades = [t for t in trade_events if t_start <= t["transaction_time"] <= t_end]
        
        if not bar_trades or not book_times:
            vpin_values.append(0.0)
            continue
            
        buy_vol = 0.0
        sell_vol = 0.0
        total_vol = 0.0
        
        for trade in bar_trades:
            p_trade = trade["price"]
            sz_trade = trade["size"]
            t_trade = trade["transaction_time"]
            
            # Find closest book state in time
            book_idx = bisect_left(book_times, t_trade)
            if book_idx >= len(all_books):
                book_idx = len(all_books) - 1
                
            closest_book = all_books[book_idx]
            
            try:
                bid_px = float(closest_book["levels"][0][0]["px"])
                ask_px = float(closest_book["levels"][1][0]["px"])
                mid_px = (bid_px + ask_px) / 2.0
            except Exception:
                mid_px = p_trade
                
            if p_trade >= mid_px:
                buy_vol += sz_trade
            else:
                sell_vol += sz_trade
            total_vol += sz_trade
            
        if total_vol > 0:
            vpin_values.append(abs(buy_vol - sell_vol) / total_vol)
        else:
            vpin_values.append(0.0)
            
    bars_df["vpin"] = vpin_values
    
    # Depth imbalance at level 1 (for compatibility with legacy models)
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
    
    # Add next-bar returns as prediction target
    bars_df["next_ret"] = bars_df["ret"].shift(-1)
    
    # Bid/Ask at the close of the bar
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
