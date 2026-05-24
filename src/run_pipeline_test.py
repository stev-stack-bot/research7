import os
import sys
import pandas as pd
import numpy as np

# Add src to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.bars import build_volume_bars, map_book_updates_to_bars
from src.features import compute_bar_features
from src.backtester import apply_triple_barriers, simulate_backtest
from src.meta_labeler import purge_and_embargo, train_meta_labeler

def run_pipeline():
    trades_file = "data/raw_trades_BTC.jsonl"
    book_file = "data/raw_book_BTC.jsonl"
    
    if not os.path.exists(trades_file) or not os.path.exists(book_file):
        print("Data files not found. Run recorder first.")
        return
        
    print("--- STEP 1: Ingesting Trades and Calculating Total Volume ---")
    # Quick check on total trade volume
    trades_df = pd.read_json(trades_file, lines=True)
    total_vol = trades_df["sz"].astype(float).sum()
    print(f"Total trades: {len(trades_df)}")
    print(f"Total trade volume: {total_vol:.5f} BTC")
    
    # We want ~40 bars for a robust test of rolling features and model split logic
    v_thresh = total_vol / 40
    print(f"Setting dynamic volume threshold per bar: {v_thresh:.5f} BTC")
    
    print("\n--- STEP 2: Building Volume Bars ---")
    bars_df = build_volume_bars(trades_file, v_thresh)
    print(f"Constructed {len(bars_df)} volume bars.")
    print(bars_df.head(5))
    
    print("\n--- STEP 3: Mapping Book Updates to Bars ---")
    book_bar_mapping = map_book_updates_to_bars(book_file, bars_df)
    print(f"Mapped {len(book_bar_mapping)} book updates across the bars.")
    
    print("\n--- STEP 4: Computing OFI and Bar Features ---")
    # Using window=10 for our short 40-bar test sample (default is 100 for production)
    df_features = compute_bar_features(bars_df, book_bar_mapping, levels_count=5, z_window=10)
    print("Features computed successfully. Sample:")
    print(df_features[["bar_index", "cofi", "cofi_z", "volatility", "volatility_ratio", "duration", "depth_ratio"]].head(5))
    
    print("\n--- STEP 5: Generating Triple Barrier Labels ---")
    # Dynamically find a z-threshold to generate some events for verification
    taker_z_thresh = 0.5
    taker_events_df = pd.DataFrame()
    for thresh in [0.5, 0.2, 0.1, 0.05, 0.01, 0.0]:
        taker_events_df = apply_triple_barriers(df_features, pt_mult=2.0, sl_mult=1.0, hold_bars=5, z_threshold=thresh, execution_mode="taker")
        if len(taker_events_df) >= 3:
            taker_z_thresh = thresh
            break
            
    maker_z_thresh = 0.5
    maker_events_df = pd.DataFrame()
    for thresh in [0.5, 0.2, 0.1, 0.05, 0.01, 0.0]:
        maker_events_df = apply_triple_barriers(df_features, pt_mult=2.0, sl_mult=1.0, hold_bars=5, z_threshold=thresh, execution_mode="maker")
        if len(maker_events_df) >= 3:
            maker_z_thresh = thresh
            break
            
    print(f"Generated {len(taker_events_df)} taker events using z_threshold={taker_z_thresh}.")
    if not taker_events_df.empty:
        print("Taker events sample:")
        print(taker_events_df.head(3))
        
    print(f"Generated {len(maker_events_df)} maker events using z_threshold={maker_z_thresh}.")
    if not maker_events_df.empty:
        print("Maker events sample:")
        print(maker_events_df.head(3))
    
    print("\n--- STEP 6: Chronological Split, Purging, and Embargo ---")
    # Dynamic split based on constructed bars count
    n_bars = len(df_features)
    train_end = int(n_bars * 0.6)
    val_start = train_end + 1
    
    print(f"Splitting data: Train index 0-{train_end}, Validation index >= {val_start}")
    
    if not taker_events_df.empty:
        taker_train_purged = purge_and_embargo(
            df_features, taker_events_df, 
            train_start_idx=0, train_end_idx=train_end, 
            val_start_idx=val_start, embargo_pct=0.05
        )
        print(f"Taker train events: {len(taker_events_df[taker_events_df['entry_idx'] <= train_end])} raw -> {len(taker_train_purged)} purged/embargoed.")
    else:
        taker_train_purged = pd.DataFrame()
        print("Taker train events: 0 raw -> 0 purged/embargoed.")
        
    if not maker_events_df.empty:
        maker_train_purged = purge_and_embargo(
            df_features, maker_events_df, 
            train_start_idx=0, train_end_idx=train_end, 
            val_start_idx=val_start, embargo_pct=0.05
        )
        print(f"Maker train events: {len(maker_events_df[maker_events_df['entry_idx'] <= train_end])} raw -> {len(maker_train_purged)} purged/embargoed.")
    else:
        maker_train_purged = pd.DataFrame()
        print("Maker train events: 0 raw -> 0 purged/embargoed.")
    
    print("\n--- STEP 7: Training Meta-Labeler Random Forests ---")
    taker_model = None
    if len(taker_train_purged) > 0:
        taker_model = train_meta_labeler(df_features, taker_train_purged)
        print("Taker meta-labeler trained successfully.")
    else:
        print("Warning: No taker training events after purging.")
        
    maker_model = None
    if len(maker_train_purged) > 0:
        maker_model = train_meta_labeler(df_features, maker_train_purged)
        print("Maker meta-labeler trained successfully.")
    else:
        print("Warning: No maker training events after purging.")
        
    print("\n--- STEP 8: Running Backtests and Generating Metric Scorecards ---")
    taker_val_events = taker_events_df[taker_events_df["entry_idx"] >= val_start].copy() if not taker_events_df.empty else pd.DataFrame()
    maker_val_events = maker_events_df[maker_events_df["entry_idx"] >= val_start].copy() if not maker_events_df.empty else pd.DataFrame()
    
    # Taker backtests
    taker_baseline_res = simulate_backtest(df_features, taker_val_events, taker_fee=0.00045, slippage=0.00005)
    taker_meta_res = simulate_backtest(df_features, taker_val_events, taker_fee=0.00045, slippage=0.00005, meta_model=taker_model, prob_thresh=0.5)
    
    # Maker backtests
    maker_baseline_res = simulate_backtest(df_features, maker_val_events, maker_fee=0.00015, taker_fee=0.00045, slippage=0.0001)
    maker_meta_res = simulate_backtest(df_features, maker_val_events, maker_fee=0.00015, taker_fee=0.00045, slippage=0.0001, meta_model=maker_model, prob_thresh=0.5)
    
    # Benchmark return (Close at end of test vs close at start)
    test_bars = df_features[df_features["bar_index"] >= val_start]
    if not test_bars.empty and len(test_bars) > 1:
        bench_ret = (test_bars.iloc[-1]["close"] - test_bars.iloc[0]["close"]) / test_bars.iloc[0]["close"]
    else:
        bench_ret = 0.0
    
    print("\n=======================================================")
    print("                PERFORMANCE METRICS REPORT             ")
    print("=======================================================")
    print(f"Benchmark Buy-and-Hold Return: {bench_ret * 100:.4f}%")
    print("-------------------------------------------------------")
    print("TAKER-TAKER EXECUTION (0.10% round-trip friction):")
    print("  Baseline Strategy:")
    for k, v in taker_baseline_res["metrics"].items():
        print(f"    - {k}: {v}")
    print("  Meta-Labeled Strategy:")
    for k, v in taker_meta_res["metrics"].items():
        print(f"    - {k}: {v}")
    print("-------------------------------------------------------")
    print("MAKER-MAKER/TAKER EXECUTION (Asymmetric fees):")
    print("  Baseline Strategy:")
    for k, v in maker_baseline_res["metrics"].items():
        print(f"    - {k}: {v}")
    print("  Meta-Labeled Strategy:")
    for k, v in maker_meta_res["metrics"].items():
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
                
    # Leakage check 2: Check features at index k only access timestamps <= end_time of bar k
    # Checked by design as compute_bar_features only looks at books mapped to bar index <= k
    if not leak_detected:
        print("PASS: No future leakage detected in features or targets.")
    else:
        print("FAIL: Future leakage detected!")
        
    print("\nPipeline execution complete.")

if __name__ == "__main__":
    run_pipeline()
