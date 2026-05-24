import sys
import os
import pandas as pd
import numpy as np
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.lighter_bars import build_lighter_volume_bars, map_lighter_book_updates_to_bars
from src.lighter_features import compute_lighter_bar_features
from src.lighter_backtester import apply_lighter_triple_barriers, simulate_lighter_backtest

def analyze_market(market_id, symbol):
    print(f"\n=======================================================")
    print(f" ANALYZING MARKET: {symbol} (Market ID: {market_id})")
    print(f"=======================================================")
    
    trades_file = f"data/raw_lighter_trades_{market_id}.jsonl"
    book_file = f"data/raw_lighter_book_{market_id}.jsonl"
    
    if not os.path.exists(trades_file) or not os.path.exists(book_file):
        print(f"Files not found for {symbol}")
        return
        
    # Ingest trades
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
    
    # 40 bars per hour
    t_start = trades_df["transaction_time"].min()
    t_end = trades_df["transaction_time"].max()
    duration_hours = (t_end - t_start) / 1000000 / 3600
    v_thresh = total_vol / (duration_hours * 40)
    print(f"Duration: {duration_hours:.2f} hours | Total Vol: {total_vol:.2f} | Bar Vol Threshold: {v_thresh:.3f}")
    
    bars_df = build_lighter_volume_bars(trades_file, v_thresh)
    book_bar_mapping = map_lighter_book_updates_to_bars(book_file, bars_df)
    
    # Reconstruct book states from already parsed mapping to avoid second file scan
    book_states = []
    seen_times = set()
    for _, row in book_bar_mapping:
        ts = row["time"]
        if ts not in seen_times:
            seen_times.add(ts)
            book_states.append({
                "time": ts,
                "bids": row["levels"][0],
                "asks": row["levels"][1]
            })
    book_states = sorted(book_states, key=lambda x: x["time"])
    trade_events = sorted(trades, key=lambda x: x["transaction_time"])
    
    df_features = compute_lighter_bar_features(bars_df, book_bar_mapping, trades, levels_count=5, z_window=10)
    
    results = []
    # Test different configurations
    z_thresholds = [0.1, 0.5, 1.0, 1.5, 2.0]
    pt_mults = [1.0, 2.0, 3.0, 5.0]
    sl_mults = [1.0, 2.0]
    hold_bars_list = [5, 10]
    
    for z in z_thresholds:
        for pt in pt_mults:
            for sl in sl_mults:
                for hold in hold_bars_list:
                    events = apply_lighter_triple_barriers(
                        df_features, book_states, trade_events,
                        pt_mult=pt, sl_mult=sl, hold_bars=hold,
                        z_threshold=z, latency_ms=300, maker_latency_ms=200
                    )
                    if events.empty:
                        continue
                    res = simulate_lighter_backtest(df_features, events, maker_fee=0.0, taker_fee=0.0, slippage=0.00005)
                    results.append({
                        "z_threshold": z,
                        "pt_mult": pt,
                        "sl_mult": sl,
                        "hold_bars": hold,
                        "trades": len(events),
                        "net_return": res["metrics"]["total_return"] * 100,
                        "pf": res["metrics"]["profit_factor"],
                        "wr": res["metrics"]["win_rate"] * 100
                    })
                    
    df_res = pd.DataFrame(results)
    if not df_res.empty:
        df_res = df_res.sort_values("net_return", ascending=False).reset_index(drop=True)
        print(f"\nTOP 10 CONFIGURATIONS FOR {symbol}:")
        print(df_res.head(10).to_string(index=False))
        
        for z in [0.5, 1.0, 1.5, 2.0]:
            print(f"\nTOP CONFIGURATIONS FOR {symbol} with z_threshold == {z}:")
            df_z = df_res[df_res["z_threshold"] == z].reset_index(drop=True)
            print(df_z.head(3).to_string(index=False))

def main():
    analyze_market(0, "ETH")
    analyze_market(1, "BTC")
    analyze_market(2, "SOL")

if __name__ == "__main__":
    main()
