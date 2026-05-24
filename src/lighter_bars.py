import json
import os
import pandas as pd
import numpy as np

def build_lighter_volume_bars(trades_file, v_thresh):
    """
    Build volume bars from Lighter trades JSON-L.
    A new bar is formed when cumulative traded volume reaches v_thresh.
    Timestamps are in microsecond epoch using transaction_time.
    """
    trades = []
    with open(trades_file, "r") as f:
        for line in f:
            msg = json.loads(line)
            trades_list = msg.get("trades") or []
            # Also check for liquidation trades
            liq_list = msg.get("liquidation_trades") or []
            for t in (trades_list + liq_list):
                trades.append({
                    "price": float(t["price"]),
                    "size": float(t["size"]),
                    "transaction_time": int(t["transaction_time"])
                })
                
    if not trades:
        raise ValueError("No trades found in Lighter trades file.")
        
    df = pd.DataFrame(trades)
    
    # Sort chronologically by transaction_time
    df = df.sort_values("transaction_time").reset_index(drop=True)
    
    bars = []
    cum_vol = 0.0
    bar_start_idx = 0
    bar_index = 0
    
    for idx, row in df.iterrows():
        cum_vol += row["size"]
        if cum_vol >= v_thresh:
            bar_trades = df.iloc[bar_start_idx : idx + 1]
            
            bar_start_time = int(bar_trades["transaction_time"].min())
            bar_end_time = int(row["transaction_time"])
            
            bars.append({
                "bar_index": bar_index,
                "start_time": bar_start_time,
                "end_time": bar_end_time,
                "open": float(bar_trades.iloc[0]["price"]),
                "high": float(bar_trades["price"].max()),
                "low": float(bar_trades["price"].min()),
                "close": float(row["price"]),
                "volume": float(bar_trades["size"].sum()),
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
            "start_time": int(bar_trades["transaction_time"].min()),
            "end_time": int(bar_trades["transaction_time"].max()),
            "open": float(bar_trades.iloc[0]["price"]),
            "high": float(bar_trades["price"].max()),
            "low": float(bar_trades["price"].min()),
            "close": float(bar_trades.iloc[-1]["price"]),
            "volume": float(bar_trades["size"].sum()),
            "trade_count": len(bar_trades)
        })
        
    return pd.DataFrame(bars)

def map_lighter_book_updates_to_bars(book_file, bars_df):
    """
    Read L2 book updates, reconstruct full book state chronologically,
    and map each state to volume bars based on last_updated_at microseconds.
    """
    states = []
    current_bids = {}
    current_asks = {}
    
    with open(book_file, "r") as f:
        for line in f:
            msg = json.loads(line)
            ob_data = msg.get("order_book", {})
            if not ob_data:
                continue
            
            # If snapshot is received, clear local state to prevent stale levels
            if len(ob_data.get("bids", [])) > 100 or len(ob_data.get("asks", [])) > 100:
                current_bids.clear()
                current_asks.clear()

            # update bids
            for b in ob_data.get("bids", []):
                price = float(b["price"])
                size = float(b["size"])
                if size == 0.0:
                    current_bids.pop(price, None)
                else:
                    current_bids[price] = size
                    
            # update asks
            for a in ob_data.get("asks", []):
                price = float(a["price"])
                size = float(a["size"])
                if size == 0.0:
                    current_asks.pop(price, None)
                else:
                    current_asks[price] = size
            
            # Prune old levels to keep dictionaries small (avoids RAM OOM and O(N log N) sorting slow downs)
            if current_bids and current_asks:
                best_bid = max(current_bids.keys())
                best_ask = min(current_asks.keys())
                mid_px = (best_bid + best_ask) / 2.0
                
                for px in list(current_bids.keys()):
                    if px < mid_px * 0.95:
                        current_bids.pop(px)
                for px in list(current_asks.keys()):
                    if px > mid_px * 1.05:
                        current_asks.pop(px)
            
            # Sort bids desc, asks asc, and slice to top 5 levels to conserve RAM
            sorted_bids = sorted([{"px": p, "sz": s} for p, s in current_bids.items()], key=lambda x: x["px"], reverse=True)[:5]
            sorted_asks = sorted([{"px": p, "sz": s} for p, s in current_asks.items()], key=lambda x: x["px"])[:5]
            
            # We must use engine's microsecond timestamp
            ts_us = int(ob_data.get("last_updated_at") or msg.get("last_updated_at"))
            
            states.append({
                "time": ts_us,
                "levels": [sorted_bids, sorted_asks]
            })
            
    # Sort raw list of dicts directly in Python (much faster than pandas)
    states.sort(key=lambda x: x["time"])
    
    # Bisect search for O(log N) mapping speed
    from bisect import bisect_right
    bar_starts = bars_df["start_time"].tolist()
    max_bar_idx = bars_df["bar_index"].max()
    
    book_bar_mapping = []
    for state in states:
        t = state["time"]
        bar_pos = bisect_right(bar_starts, t) - 1
        if bar_pos >= 0:
            bar_idx = bar_pos
            if t <= bars_df.loc[bar_idx, "end_time"]:
                book_bar_mapping.append((bar_idx, state))
            elif t > bars_df["end_time"].max():
                book_bar_mapping.append((max_bar_idx, state))
        else:
            if t > bars_df["end_time"].max():
                book_bar_mapping.append((max_bar_idx, state))
                
    return book_bar_mapping


