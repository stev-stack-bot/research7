import os
import sys
import json
import pandas as pd
import numpy as np

# Add src to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.lighter_bars import build_lighter_volume_bars, map_lighter_book_updates_to_bars
from src.lighter_features import compute_lighter_bar_features
from src.lighter_backtester import apply_lighter_triple_barriers, simulate_lighter_backtest

def main():
    trades_file = "data/raw_lighter_trades_0.jsonl"
    book_file = "data/raw_lighter_book_0.jsonl"
    
    if not os.path.exists(trades_file) or not os.path.exists(book_file):
        print("Data files not found.")
        return
        
    print("Loading data...")
    # Load trades
    trades = []
    with open(trades_file, "r") as f:
        for line in f:
            msg = json.loads(line)
            trades_list = msg.get("trades") or []
            liq_list = msg.get("liquidation_trades") or []
            for t in (trades_list + liq_list):
                trades.append({
                    "price": float(t["price"]),
                    "size": float(t["size"]),
                    "transaction_time": int(t["transaction_time"])
                })
    trades_df = pd.DataFrame(trades).sort_values("transaction_time").reset_index(drop=True)
    total_vol = trades_df["size"].sum()
    
    # Build bars (we will try dynamic thresholds to get about 50 bars)
    v_thresh = total_vol / 50
    bars_df = build_lighter_volume_bars(trades_file, v_thresh)
    book_bar_mapping = map_lighter_book_updates_to_bars(book_file, bars_df)
    
    # Reconstruct book states
    book_states = []
    current_bids = {}
    current_asks = {}
    with open(book_file, "r") as f:
        for line in f:
            msg = json.loads(line)
            ob_data = msg.get("order_book", {})
            if not ob_data:
                continue
            for b in ob_data.get("bids", []):
                price = float(b["price"])
                size = float(b["size"])
                if size == 0.0:
                    current_bids.pop(price, None)
                else:
                    current_bids[price] = size
            for a in ob_data.get("asks", []):
                price = float(a["price"])
                size = float(a["size"])
                if size == 0.0:
                    current_asks.pop(price, None)
                else:
                    current_asks[price] = size
            sorted_bids = sorted([{"px": p, "sz": s} for p, s in current_bids.items()], key=lambda x: x["px"], reverse=True)
            sorted_asks = sorted([{"px": p, "sz": s} for p, s in current_asks.items()], key=lambda x: x["px"])
            ts_us = int(ob_data.get("last_updated_at") or msg.get("last_updated_at"))
            book_states.append({
                "time": ts_us,
                "bids": sorted_bids,
                "asks": sorted_asks
            })
    book_states = sorted(book_states, key=lambda x: x["time"])
    trade_events = sorted(trades, key=lambda x: x["transaction_time"])
    
    # Compute features using z_window = 10
    df_features = compute_lighter_bar_features(bars_df, book_bar_mapping, trades, levels_count=5, z_window=10)

    
    results = []
    
    # Param sweep
    z_thresholds = [0.1, 0.5, 1.0, 1.5, 2.0]
    pt_mults = [1.0, 2.0, 3.0, 5.0]
    sl_mults = [1.0, 2.0]
    hold_bars_list = [5, 10]
    
    print("Starting grid search...")
    for z_thresh in z_thresholds:
        for pt in pt_mults:
            for sl in sl_mults:
                for hold in hold_bars_list:
                    # Run standard barriers
                    events = apply_lighter_triple_barriers(
                        df_features, book_states, trade_events,
                        pt_mult=pt, sl_mult=sl, hold_bars=hold,
                        z_threshold=z_thresh, latency_ms=300, maker_latency_ms=200
                    )
                    
                    if events.empty:
                        continue
                        
                    # Standard tier backtest (0% fees, 0.5 bps slippage)
                    res_std = simulate_lighter_backtest(df_features, events, maker_fee=0.0, taker_fee=0.0, slippage=0.00005)
                    # Premium tier backtest (2.8 bps taker / 0.4 bps maker, 0.2 bps slippage)
                    res_prem = simulate_lighter_backtest(df_features, events, maker_fee=0.00004, taker_fee=0.00028, slippage=0.00002)
                    
                    results.append({
                        "z_threshold": z_thresh,
                        "pt_mult": pt,
                        "sl_mult": sl,
                        "hold_bars": hold,
                        "trades": len(events),
                        "std_return": res_std["metrics"]["total_return"] * 100,
                        "std_pf": res_std["metrics"]["profit_factor"],
                        "std_wr": res_std["metrics"]["win_rate"] * 100,
                        "prem_return": res_prem["metrics"]["total_return"] * 100,
                        "prem_pf": res_prem["metrics"]["profit_factor"],
                        "prem_wr": res_prem["metrics"]["win_rate"] * 100
                    })
                    
    df_results = pd.DataFrame(results)
    if not df_results.empty:
        # Sort by standard return descending
        df_results = df_results.sort_values("std_return", ascending=False).reset_index(drop=True)
        print("\nTOP 15 PARAMETER CONFIGURATIONS (Sorted by Standard Return):")
        print(df_results.head(15).to_string(index=False))
        
        # Save to csv
        df_results.to_csv("data/optimization_results.csv", index=False)
        print("\nResults saved to data/optimization_results.csv")
    else:
        print("No configurations generated any events.")

if __name__ == "__main__":
    main()
