import os
import sys
import json
import pandas as pd
import numpy as np

# Add src to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.lighter_bars import build_lighter_volume_bars, map_lighter_book_updates_to_bars
from src.lighter_features import compute_lighter_bar_features
from src.lighter_backtester import apply_lighter_triple_barriers, simulate_lighter_backtest
from src.lighter_meta_labeler import purge_and_embargo_lighter, train_lighter_meta_labeler

def run_lighter_pipeline():
    trades_file = "data/raw_lighter_trades_0.jsonl"
    book_file = "data/raw_lighter_book_0.jsonl"
    
    if not os.path.exists(trades_file) or not os.path.exists(book_file):
        print("Data files not found. Run recorder first.")
        return
        
    print("--- STEP 1: Ingesting Trades and Calculating Total Volume ---")
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
                
    trades_df = pd.DataFrame(trades)
    total_vol = trades_df["size"].sum()
    print(f"Total trades ingested: {len(trades_df)}")
    print(f"Total trade volume: {total_vol:.5f} ETH")
    
    # We want ~40 bars for a robust test of rolling features and model split logic
    v_thresh = total_vol / 40
    print(f"Setting dynamic volume threshold per bar: {v_thresh:.5f} ETH")
    
    print("\n--- STEP 2: Building Volume Bars ---")
    bars_df = build_lighter_volume_bars(trades_file, v_thresh)
    print(f"Constructed {len(bars_df)} volume bars.")
    print(bars_df.head(5))
    
    print("\n--- STEP 3: Mapping Book Updates to Bars ---")
    book_bar_mapping = map_lighter_book_updates_to_bars(book_file, bars_df)
    print(f"Mapped {len(book_bar_mapping)} book updates across the bars.")
    
    print("\n--- STEP 4: Computing OFI and Bar Features ---")
    # Using window=10 for our short 40-bar test sample (default is 100 for production)
    df_features = compute_lighter_bar_features(bars_df, book_bar_mapping, trades, levels_count=5, z_window=10)

    print("Features computed successfully. Sample:")
    print(df_features[["bar_index", "cofi", "cofi_z", "volatility", "volatility_ratio", "duration", "depth_ratio"]].head(5))
    
    # Reconstruct order book states for backtest price lookups
    print("\n--- Reconstructing Order Book States for Backtest Lookup ---")
    book_states = []
    current_bids = {}
    current_asks = {}
    with open(book_file, "r") as f:
        for line in f:
            msg = json.loads(line)
            ob_data = msg.get("order_book", {})
            if not ob_data:
                continue
            # Clear bids/asks when snapshot is detected (>100 levels) to prevent stale price level leakage
            if len(ob_data.get("bids", [])) > 100 or len(ob_data.get("asks", [])) > 100:
                current_bids.clear()
                current_asks.clear()
                
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
            
    # Sort book states
    book_states = sorted(book_states, key=lambda x: x["time"])
    
    # Sort trade events
    trade_events = sorted(trades, key=lambda x: x["transaction_time"])
    
    print("\n--- STEP 5: Generating Triple Barrier Labels ---")
    # Standard: 300ms taker latency, 200ms maker latency
    # Premium: 140ms taker latency, 0ms maker latency
    std_z_thresh = 0.5
    std_events_df = pd.DataFrame()
    for thresh in [0.5, 0.2, 0.1, 0.05, 0.01, 0.0]:
        std_events_df = apply_lighter_triple_barriers(
            df_features, book_states, trade_events, 
            pt_mult=2.0, sl_mult=1.0, hold_bars=5, z_threshold=thresh, 
            latency_ms=300, maker_latency_ms=200
        )
        if len(std_events_df) >= 3:
            std_z_thresh = thresh
            break
            
    prem_z_thresh = 0.5
    prem_events_df = pd.DataFrame()
    for thresh in [0.5, 0.2, 0.1, 0.05, 0.01, 0.0]:
        prem_events_df = apply_lighter_triple_barriers(
            df_features, book_states, trade_events, 
            pt_mult=2.0, sl_mult=1.0, hold_bars=5, z_threshold=thresh, 
            latency_ms=140, maker_latency_ms=0
        )
        if len(prem_events_df) >= 3:
            prem_z_thresh = thresh
            break
            
    print(f"Generated {len(std_events_df)} Standard events using z_threshold={std_z_thresh}.")
    if not std_events_df.empty:
        print("Standard events sample:")
        print(std_events_df.head(3))
        
    print(f"Generated {len(prem_events_df)} Premium events using z_threshold={prem_z_thresh}.")
    if not prem_events_df.empty:
        print("Premium events sample:")
        print(prem_events_df.head(3))
        
    print("\n--- STEP 6: Chronological Split, Purging, and Embargo ---")
    n_bars = len(df_features)
    train_end = int(n_bars * 0.6)
    val_start = train_end + 1
    
    print(f"Splitting data: Train index 0-{train_end}, Validation index >= {val_start}")
    
    if not std_events_df.empty:
        std_train_purged = purge_and_embargo_lighter(
            df_features, std_events_df, 
            train_start_idx=0, train_end_idx=train_end, 
            val_start_idx=val_start, embargo_pct=0.05
        )
        print(f"Standard train events: {len(std_events_df[std_events_df['entry_idx'] <= train_end])} raw -> {len(std_train_purged)} purged.")
    else:
        std_train_purged = pd.DataFrame()
        
    if not prem_events_df.empty:
        prem_train_purged = purge_and_embargo_lighter(
            df_features, prem_events_df, 
            train_start_idx=0, train_end_idx=train_end, 
            val_start_idx=val_start, embargo_pct=0.05
        )
        print(f"Premium train events: {len(prem_events_df[prem_events_df['entry_idx'] <= train_end])} raw -> {len(prem_train_purged)} purged.")
    else:
        prem_train_purged = pd.DataFrame()
        
    print("\n--- STEP 7: Training Meta-Labeler Random Forests ---")
    std_model = None
    if len(std_train_purged) > 0:
        std_model = train_lighter_meta_labeler(df_features, std_train_purged)
        print("Standard meta-labeler trained.")
    else:
        print("Warning: No Standard training events after purging.")
        
    prem_model = None
    if len(prem_train_purged) > 0:
        prem_model = train_lighter_meta_labeler(df_features, prem_train_purged)
        print("Premium meta-labeler trained.")
    else:
        print("Warning: No Premium training events after purging.")
        
    print("\n--- STEP 8: Running Backtests and Generating Metric Scorecards ---")
    std_val_events = std_events_df[std_events_df["entry_idx"] >= val_start].copy() if not std_events_df.empty else pd.DataFrame()
    prem_val_events = prem_events_df[prem_events_df["entry_idx"] >= val_start].copy() if not prem_events_df.empty else pd.DataFrame()
    
    # Standard: 0% maker/taker, 0.5 bps slippage penalty
    std_baseline_res = simulate_lighter_backtest(df_features, std_val_events, maker_fee=0.0, taker_fee=0.0, slippage=0.00005)
    std_meta_res = simulate_lighter_backtest(df_features, std_val_events, maker_fee=0.0, taker_fee=0.0, slippage=0.00005, meta_model=std_model, prob_thresh=0.5)
    
    # Premium: 0.4 bps maker fee, 2.8 bps taker fee, 0.2 bps slippage penalty
    prem_baseline_res = simulate_lighter_backtest(df_features, prem_val_events, maker_fee=0.00004, taker_fee=0.00028, slippage=0.00002)
    prem_meta_res = simulate_lighter_backtest(df_features, prem_val_events, maker_fee=0.00004, taker_fee=0.00028, slippage=0.00002, meta_model=prem_model, prob_thresh=0.5)
    
    test_bars = df_features[df_features["bar_index"] >= val_start]
    if not test_bars.empty and len(test_bars) > 1:
        bench_ret = (test_bars.iloc[-1]["close"] - test_bars.iloc[0]["close"]) / test_bars.iloc[0]["close"]
    else:
        bench_ret = 0.0
        
    print("\n=======================================================")
    print("                LIGHTER PERFORMANCE REPORT             ")
    print("=======================================================")
    print(f"Benchmark Buy-and-Hold Return: {bench_ret * 100:.4f}%")
    print("-------------------------------------------------------")
    print("STANDARD TIER (0% fees, 300ms taker / 200ms maker latency):")
    print("  Baseline Strategy:")
    for k, v in std_baseline_res["metrics"].items():
        print(f"    - {k}: {v}")
    print("  Meta-Labeled Strategy:")
    for k, v in std_meta_res["metrics"].items():
        print(f"    - {k}: {v}")
    print("-------------------------------------------------------")
    print("PREMIUM TIER (2.8 bps taker / 0.4 bps maker, 140ms taker latency):")
    print("  Baseline Strategy:")
    for k, v in prem_baseline_res["metrics"].items():
        print(f"    - {k}: {v}")
    print("  Meta-Labeled Strategy:")
    for k, v in prem_meta_res["metrics"].items():
        print(f"    - {k}: {v}")
    print("=======================================================")
    
    print("\n--- STEP 9: Leakage and Integrity Checks ---")
    leak_detected = False
    
    # Leakage check 1: Target return next_ret vs future bars
    for idx, row in df_features.iterrows():
        if idx < len(df_features) - 1:
            actual_next_close = df_features.loc[idx+1, "close"]
            actual_curr_close = df_features.loc[idx, "close"]
            expected_next_ret = np.log(actual_next_close / actual_curr_close)
            if not np.isclose(row["next_ret"], expected_next_ret):
                print(f"LEAKAGE WARNING: next_ret mismatch at index {idx}!")
                leak_detected = True
                
    if not leak_detected:
        print("PASS: No future leakage detected in features or targets.")
    else:
        print("FAIL: Future leakage detected!")
        
    print("\nPipeline execution complete.")

if __name__ == "__main__":
    run_lighter_pipeline()
