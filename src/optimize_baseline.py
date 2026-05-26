import os
import sys
import glob
import io
import json
import numpy as np
import pandas as pd
import zstandard as zstd

# Add src to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.run_lighter_pipeline_v3 import (
    MARKET_PARAMS, stream_jsonl_zst, build_volume_bars_from_events,
    compute_bar_features_streaming
)

def get_confluence_signals(df, z_threshold, min_score):
    signals = []
    cofi_z_vals = df["cofi_z"].values
    micro_ret_vals = df["micro_ret"].values
    kyle_lambda_vals = df["kyle_lambda"].values
    depth_ratio_vals = df["depth_ratio"].values
    autocorr_vals = df["autocorr_ret"].values
    bar_indices = df["bar_index"].values
    
    for idx in range(len(df)):
        cofi_z = cofi_z_vals[idx]
        micro_ret = micro_ret_vals[idx]
        kyle_lambda = kyle_lambda_vals[idx]
        depth_ratio = depth_ratio_vals[idx]
        autocorr = autocorr_vals[idx]
        
        # Check Long
        score_long = 0
        if cofi_z >= z_threshold:
            score_long += 1
        if micro_ret > 0:
            score_long += 1
        if kyle_lambda > 0:
            score_long += 1
        if depth_ratio > 1.0:
            score_long += 1
        if autocorr > 0:
            score_long += 1
            
        # Check Short
        score_short = 0
        if cofi_z <= -z_threshold:
            score_short += 1
        if micro_ret < 0:
            score_short += 1
        if kyle_lambda < 0:
            score_short += 1
        if depth_ratio < 1.0:
            score_short += 1
        if autocorr > 0:
            score_short += 1
            
        if cofi_z >= z_threshold and score_long >= min_score:
            signals.append((idx, 1))
        elif cofi_z <= -z_threshold and score_short >= min_score:
            signals.append((idx, -1))
            
    return signals

def simulate_single_signal(idx, direction, df, book_times, best_bids, best_asks, trade_times, trade_prices, pt_mult, sl_mult, hold_bars, latency_ms, maker_latency_ms):
    row = df.loc[idx]
    signal_time = row["end_time"]
    vol = row["volatility"]
    
    t_entry_exec = signal_time + latency_ms * 1000
    book_idx = np.searchsorted(book_times, t_entry_exec)
    if book_idx >= len(book_times):
        return None
        
    entry_price = best_asks[book_idx] if direction == 1 else best_bids[book_idx]
    
    start_times = df["start_time"].values
    end_times = df["end_time"].values
    
    entry_bar_idx_pos = np.searchsorted(start_times, t_entry_exec, side='right') - 1
    if entry_bar_idx_pos >= 0 and t_entry_exec <= end_times[entry_bar_idx_pos]:
        entry_idx = entry_bar_idx_pos
    else:
        if t_entry_exec > end_times[-1]:
            return None
        entry_idx = idx
        
    pt_barrier = entry_price * (1 + pt_mult * vol * direction)
    sl_barrier = entry_price * (1 - sl_mult * vol * direction)
    
    t_maker_active = t_entry_exec + maker_latency_ms * 1000
    
    expiry_bar_idx = min(entry_idx + hold_bars, len(df) - 1)
    t_expiry = df.loc[expiry_bar_idx, "end_time"]
    
    first_trade_idx = np.searchsorted(trade_times, t_entry_exec)
    
    exit_time = t_expiry
    exit_type = "time"
    
    for k in range(first_trade_idx, len(trade_times)):
        t_trade = trade_times[k]
        if t_trade > t_expiry:
            break
            
        p_trade = trade_prices[k]
        
        if direction == 1 and p_trade <= sl_barrier:
            exit_time = t_trade
            exit_type = "sl"
            break
        elif direction == -1 and p_trade >= sl_barrier:
            exit_time = t_trade
            exit_type = "sl"
            break
            
        if t_trade >= t_maker_active:
            if direction == 1 and p_trade >= pt_barrier:
                exit_time = t_trade
                exit_type = "pt"
                break
            elif direction == -1 and p_trade <= pt_barrier:
                exit_time = t_trade
                exit_type = "pt"
                break
                
    if exit_type == "pt":
        exit_price = pt_barrier
    elif exit_type == "sl":
        t_trigger_exec = exit_time + latency_ms * 1000
        exit_book_idx = np.searchsorted(book_times, t_trigger_exec)
        if exit_book_idx < len(book_times):
            exit_price = best_bids[exit_book_idx] if direction == 1 else best_asks[exit_book_idx]
        else:
            exit_price = sl_barrier
    else:
        t_expiry_exec = t_expiry + latency_ms * 1000
        exit_book_idx = np.searchsorted(book_times, t_expiry_exec)
        if exit_book_idx < len(book_times):
            exit_price = best_bids[exit_book_idx] if direction == 1 else best_asks[exit_book_idx]
        else:
            exit_price = df.loc[expiry_bar_idx, "close"]
            
    exit_bar_idx_pos = np.searchsorted(start_times, exit_time, side='right') - 1
    if exit_bar_idx_pos >= 0 and exit_time <= end_times[exit_bar_idx_pos]:
        exit_idx = exit_bar_idx_pos
    else:
        exit_idx = len(df) - 1
        
    raw_ret = (exit_price - entry_price) / entry_price * direction
    return {
        "entry_idx": entry_idx,
        "signal_idx": idx,
        "direction": direction,
        "exit_idx": exit_idx,
        "exit_time": exit_time,
        "exit_type": exit_type,
        "raw_return": raw_ret,
        "label": 1 if exit_type == "pt" else 0
    }

def evaluate_baseline_returns(events, df, maker_fee=0.0, taker_fee=0.0, slippage=0.0):
    if not events:
        return 0.0, 0
    
    net_returns = []
    for ev in events:
        exit_type = ev["exit_type"]
        if exit_type == "pt":
            cost = taker_fee + maker_fee + slippage
        else:
            cost = taker_fee + taker_fee + slippage * 2
        net_returns.append(ev["raw_return"] - cost)
        
    return float(sum(net_returns)), len(net_returns)

def run_grid_search(symbol):
    params = MARKET_PARAMS[symbol]
    mid = params["market_id"]
    
    data_dir = "data"
    trade_files = sorted(glob.glob(os.path.join(data_dir, f"raw_lighter_trades_{mid}_*.jsonl.zst")))
    book_files = sorted(glob.glob(os.path.join(data_dir, f"raw_lighter_book_{mid}_*.jsonl.zst")))
    
    if not trade_files or not book_files:
        print(f"No files for {symbol}")
        return None
        
    # Ingest trades
    trades = []
    for f in trade_files:
        for msg in stream_jsonl_zst([f]):
            trades_list = msg.get("trades") or []
            liq_list = msg.get("liquidation_trades") or []
            for t in (trades_list + liq_list):
                trades.append({
                    "price": float(t["price"]),
                    "size": float(t["size"]),
                    "transaction_time": int(t["transaction_time"])
                })
    trades.sort(key=lambda x: x["transaction_time"])
    
    v_thresh = params["v_thresh"]
    bars_df = build_volume_bars_from_events(trades, v_thresh)
    df_features, book_times, best_bids, best_asks = compute_bar_features_streaming(
        bars_df, book_files, trades, z_window=100
    )
    
    # Split into Train (first 60%)
    n_bars = len(df_features)
    train_end = int(n_bars * 0.6)
    
    df_train = df_features.iloc[:train_end+1].copy()
    df_val = df_features.iloc[train_end+1:].copy()
    
    trade_times = np.array([t["transaction_time"] for t in trades], dtype=np.int64)
    trade_prices = np.array([t["price"] for t in trades], dtype=np.float64)
    
    # Parameter grid to search
    z_thresholds = [0.5, 1.0, 1.5]
    min_scores = [1, 2, 3]
    pt_mults = [1.0, 2.0, 3.0, 5.0]
    sl_mults = [0.5, 1.0, 1.5, 2.0]
    hold_bars_list = [3, 5, 10, 15]
    
    # Standard Tier: 0% maker/taker, 0.5 bps slippage
    maker_fee = 0.0
    taker_fee = 0.0
    slippage = 0.00005
    latency_ms = 300
    maker_latency_ms = 200
    
    best_ret = -999.0
    best_params = None
    best_train_events = []
    
    print(f"\nSearching parameter space for {symbol} standard tier (min trades >= 10 in train)...")
    
    # Pre-calculate confluence signals for all z_threshold and min_score pairs
    signal_cache = {}
    for z in z_thresholds:
        for ms in min_scores:
            signals = get_confluence_signals(df_train, z, ms)
            signal_cache[(z, ms)] = signals
            
    # Run Grid Search
    count = 0
    for (z, ms), signals in signal_cache.items():
        if not signals:
            continue
            
        for pt in pt_mults:
            for sl in sl_mults:
                for hb in hold_bars_list:
                    # Simulate all signals
                    events = []
                    for idx, direction in signals:
                        res = simulate_single_signal(
                            idx, direction, df_train, book_times, best_bids, best_asks, 
                            trade_times, trade_prices, pt, sl, hb, latency_ms, maker_latency_ms
                        )
                        if res:
                            events.append(res)
                            
                    tot_ret, n_trades = evaluate_baseline_returns(events, df_train, maker_fee, taker_fee, slippage)
                    
                    if n_trades >= 10:  # Minimum trade count constraint to avoid overfitting to 1 trade
                        if tot_ret > best_ret:
                            best_ret = tot_ret
                            best_params = {
                                "z_threshold": z,
                                "min_score": ms,
                                "pt_mult": pt,
                                "sl_mult": sl,
                                "hold_bars": hb
                            }
                            best_train_events = events
                    count += 1
                    
    print(f"Finished {count} grid evaluations. Best train return: {best_ret*100:+.4f}%")
    print(f"Best Params: {best_params}")
    
    # Evaluate best params on validation set
    if best_params:
        val_signals = get_confluence_signals(df_features, best_params["z_threshold"], best_params["min_score"])
        # Filter for validation signals only
        val_signals = [(idx, dir) for idx, dir in val_signals if idx > train_end]
        
        val_events = []
        for idx, direction in val_signals:
            res = simulate_single_signal(
                idx, direction, df_features, book_times, best_bids, best_asks, 
                trade_times, trade_prices, best_params["pt_mult"], best_params["sl_mult"], 
                best_params["hold_bars"], latency_ms, maker_latency_ms
            )
            if res:
                val_events.append(res)
                
        val_ret, val_n = evaluate_baseline_returns(val_events, df_features, maker_fee, taker_fee, slippage)
        print(f"Validation Performance: Return = {val_ret*100:+.4f}% | Trades = {val_n}")
        
        return {
            "symbol": symbol,
            "best_params": best_params,
            "train_ret": best_ret,
            "val_ret": val_ret,
            "val_trades": val_n
        }
    return None

def main():
    for sym in ["ETH", "BTC", "SOL"]:
        print(f"\n=======================================================")
        print(f" OPTIMIZING MARKET BASELINE: {sym}")
        print(f"=======================================================")
        run_grid_search(sym)

if __name__ == "__main__":
    main()
