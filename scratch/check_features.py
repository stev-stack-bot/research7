import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
import pandas as pd
import numpy as np

from src.lighter_bars import build_lighter_volume_bars, map_lighter_book_updates_to_bars
from src.lighter_features import compute_lighter_bar_features

def analyze_market(market_id, symbol, v_thresh):
    trades_file = f"data/raw_lighter_trades_{market_id}.jsonl"
    book_file = f"data/raw_lighter_book_{market_id}.jsonl"
    
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
    
    bars_df = build_lighter_volume_bars(trades_file, v_thresh)
    book_bar_mapping = map_lighter_book_updates_to_bars(book_file, bars_df)
    
    df_features = compute_lighter_bar_features(bars_df, book_bar_mapping, trades, levels_count=5, z_window=10)
    
    print(f"\n=== FEATURE ANALYSIS FOR {symbol} ===")
    print(f"Number of bars: {len(df_features)}")
    print(df_features[["close", "volatility", "cofi_z", "avg_spread"]].describe())

def main():
    analyze_market(0, "ETH", 78.4)
    analyze_market(1, "BTC", 3.43)

if __name__ == "__main__":
    main()
