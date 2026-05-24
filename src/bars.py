import json
import os
import pandas as pd
import numpy as np

def build_volume_bars(trades_file, v_thresh):
    """
    Build volume bars from trades JSON-L.
    A new bar is formed when cumulative traded volume reaches v_thresh.
    """
    trades = []
    with open(trades_file, "r") as f:
        for line in f:
            trades.append(json.loads(line))
            
    if not trades:
        raise ValueError("No trades found in file.")
        
    df = pd.DataFrame(trades)
    df["px"] = df["px"].astype(float)
    df["sz"] = df["sz"].astype(float)
    df["time"] = df["time"].astype(int)
    
    # Sort chronologically
    df = df.sort_values("time").reset_index(drop=True)
    
    bars = []
    cum_vol = 0.0
    bar_start_idx = 0
    bar_index = 0
    
    for idx, row in df.iterrows():
        cum_vol += row["sz"]
        if cum_vol >= v_thresh:
            bar_trades = df.iloc[bar_start_idx : idx + 1]
            
            bar_start_time = int(bar_trades["time"].min())
            bar_end_time = int(row["time"])
            
            bars.append({
                "bar_index": bar_index,
                "start_time": bar_start_time,
                "end_time": bar_end_time,
                "open": float(bar_trades.iloc[0]["px"]),
                "high": float(bar_trades["px"].max()),
                "low": float(bar_trades["px"].min()),
                "close": float(row["px"]),
                "volume": float(bar_trades["sz"].sum()),
                "trade_count": len(bar_trades)
            })
            
            cum_vol = 0.0
            bar_start_idx = idx + 1
            bar_index += 1
            
    # Include remaining partial bar if any
    if bar_start_idx < len(df):
        bar_trades = df.iloc[bar_start_idx:]
        bars.append({
            "bar_index": bar_index,
            "start_time": int(bar_trades["time"].min()),
            "end_time": int(bar_trades["time"].max()),
            "open": float(bar_trades.iloc[0]["px"]),
            "high": float(bar_trades["px"].max()),
            "low": float(bar_trades["px"].min()),
            "close": float(bar_trades.iloc[-1]["px"]),
            "volume": float(bar_trades["sz"].sum()),
            "trade_count": len(bar_trades)
        })
        
    return pd.DataFrame(bars)

def map_book_updates_to_bars(book_file, bars_df):
    """
    Read L2 book updates and assign them to volume bars based on timestamps.
    A book update belongs to bar k if start_time <= update_time <= end_time.
    """
    books = []
    with open(book_file, "r") as f:
        for line in f:
            books.append(json.loads(line))
            
    if not books:
        raise ValueError("No book updates found in file.")
        
    df_books = pd.DataFrame(books)
    df_books["time"] = df_books["time"].astype(int)
    
    # Sort chronologically
    df_books = df_books.sort_values("time").reset_index(drop=True)
    
    # Map using pandas merge_asof or interval logic
    # To be extremely explicit and robust, we do a manual interval mapping
    book_bar_mapping = []
    
    for idx, row in df_books.iterrows():
        t = row["time"]
        # Find which bar this belongs to
        # A book update at time t belongs to the active bar k
        matching_bars = bars_df[(bars_df["start_time"] <= t) & (t <= bars_df["end_time"])]
        if not matching_bars.empty:
            bar_idx = matching_bars.iloc[0]["bar_index"]
            book_bar_mapping.append((bar_idx, row))
        else:
            # If t is before the first bar start, it's discarded or pre-bar
            # If t is after the last bar end, assign it to the last bar
            if t > bars_df["end_time"].max():
                book_bar_mapping.append((bars_df["bar_index"].max(), row))
                
    return book_bar_mapping
