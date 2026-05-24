import sys
import os
import pandas as pd
import numpy as np
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.lighter_bars import build_lighter_volume_bars, map_lighter_book_updates_to_bars
from src.lighter_features import compute_lighter_bar_features
from src.lighter_backtester import apply_lighter_triple_barriers, simulate_lighter_backtest

def run_filtered_backtest(df_features, book_states, trade_events, z_thresh, pt, sl, hold, spread_limit_mult=None, vpin_limit=None):
    # Apply standard barriers
    events = apply_lighter_triple_barriers(
        df_features, book_states, trade_events,
        pt_mult=pt, sl_mult=sl, hold_bars=hold,
        z_threshold=z_thresh, latency_ms=300, maker_latency_ms=200
    )
    if events.empty:
        return None
        
    # Apply filters to events
    filtered_rows = []
    rolling_spread_mean = df_features["avg_spread"].rolling(10, min_periods=1).mean()
    
    for idx, row in events.iterrows():
        sig_idx = int(row["signal_idx"])
        spread = df_features.loc[sig_idx, "avg_spread"]
        vpin = df_features.loc[sig_idx, "vpin"]
        mean_spread = rolling_spread_mean.loc[sig_idx]
        
        # Spread Filter
        if spread_limit_mult is not None and spread > spread_limit_mult * mean_spread:
            continue
            
        # VPIN Filter
        if vpin_limit is not None and vpin > vpin_limit:
            continue
            
        filtered_rows.append(row)
        
    if not filtered_rows:
        return None
        
    filtered_events = pd.DataFrame(filtered_rows).reset_index(drop=True)
    res = simulate_lighter_backtest(df_features, filtered_events, maker_fee=0.0, taker_fee=0.0, slippage=0.00005)
    return {
        "trades": len(filtered_events),
        "net_return": res["metrics"]["total_return"] * 100,
        "pf": res["metrics"]["profit_factor"],
        "wr": res["metrics"]["win_rate"] * 100
    }

def analyze_market_filters(market_id, symbol):
    print(f"\n=======================================================")
    print(f" TESTING FILTERS FOR: {symbol}")
    print(f"=======================================================")
    
    trades_file = f"data/raw_lighter_trades_{market_id}.jsonl"
    book_file = f"data/raw_lighter_book_{market_id}.jsonl"
    
    if not os.path.exists(trades_file) or not os.path.exists(book_file):
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
    
    bars_df = build_lighter_volume_bars(trades_file, v_thresh)
    book_bar_mapping = map_lighter_book_updates_to_bars(book_file, bars_df)
    
    # Reconstruct book states
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
    
    # Grid search filters
    z_options = [0.5, 1.0, 1.5, 2.0]
    spread_options = [1.0, 1.2, 1.5, None]
    vpin_options = [0.4, 0.6, 0.8, None]
    
    # Parameters based on previously found optimums
    if symbol == "BTC":
        pt, sl, hold = 5.0, 2.0, 10
    elif symbol == "ETH":
        pt, sl, hold = 1.0, 1.0, 10
    else:  # SOL
        pt, sl, hold = 2.0, 2.0, 5
        
    results = []
    for z in z_options:
        for spread_mult in spread_options:
            for vpin in vpin_options:
                res = run_filtered_backtest(df_features, book_states, trade_events, z, pt, sl, hold, spread_mult, vpin)
                if res:
                    results.append({
                        "z_threshold": z,
                        "spread_mult": spread_mult,
                        "vpin_limit": vpin,
                        "trades": res["trades"],
                        "net_return": res["net_return"],
                        "pf": res["pf"],
                        "wr": res["wr"]
                    })
                    
    df_res = pd.DataFrame(results)
    if not df_res.empty:
        df_res = df_res.sort_values("net_return", ascending=False).reset_index(drop=True)
        print(f"Top 10 Filtered Configurations for {symbol}:")
        print(df_res.head(10).to_string(index=False))
        
        print(f"\nBaseline (No Filters) for {symbol}:")
        df_base = df_res[(df_res["spread_mult"].isna()) & (df_res["vpin_limit"].isna())]
        print(df_base.to_string(index=False))

def main():
    analyze_market_filters(0, "ETH")
    analyze_market_filters(1, "BTC")
    analyze_market_filters(2, "SOL")

if __name__ == "__main__":
    main()
