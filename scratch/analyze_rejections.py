import os
import sys
import numpy as np
import pandas as pd
import glob
from sklearn.ensemble import RandomForestClassifier

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.run_lighter_pipeline_v3 import stream_jsonl_zst, build_volume_bars_from_events, compute_bar_features_streaming
from src.run_lighter_pipeline_v5 import ASYMM_PARAMS, apply_lighter_triple_barriers_v5, train_lighter_meta_labeler_v5

def analyze_market_rejections(symbol):
    asym_params = ASYMM_PARAMS[symbol]
    mid = asym_params["market_id"]
    
    data_dir = "data"
    trade_files = sorted(glob.glob(os.path.join(data_dir, f"raw_lighter_trades_{mid}_*.jsonl.zst")))
    book_files = sorted(glob.glob(os.path.join(data_dir, f"raw_lighter_book_{mid}_*.jsonl.zst")))
    
    if not trade_files or not book_files:
        print(f"No data files found for {symbol}.")
        return
        
    print(f"\n=======================================================")
    print(f" DIAGNOSING VETO ANALYSIS FOR {symbol}")
    print(f"=======================================================")
    
    # 1. Ingest Trades
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
    
    # 2. Build bars and features
    v_thresh = asym_params["v_thresh"]
    bars_df = build_volume_bars_from_events(trades, v_thresh)
    df_features, book_times, best_bids, best_asks = compute_bar_features_streaming(
        bars_df, book_files, trades, z_window=100
    )
    
    # 3. Apply Asymmetric Barriers
    std_events = apply_lighter_triple_barriers_v5(
        df_features, book_times, best_bids, best_asks, trades,
        asymm_params=asym_params, latency_ms=300, maker_latency_ms=200,
        maker_fee=0.0, taker_fee=0.0, slippage=0.00005
    )
    
    prem_events = apply_lighter_triple_barriers_v5(
        df_features, book_times, best_bids, best_asks, trades,
        asymm_params=asym_params, latency_ms=140, maker_latency_ms=0,
        maker_fee=0.00004, taker_fee=0.00028, slippage=0.00002
    )
    
    n_bars = len(df_features)
    train_end = int(n_bars * 0.6)
    val_start = train_end + 1
    
    # Feature columns
    FEATURE_COLS = [
        "volatility_ratio", "kyle_lambda", "gini_coefficient", "ret_lag2",
        "tick_efficiency", "duration", "hurst", "amihud", "ret_lag1",
        "velocity", "avg_spread", "micro_ret", "autocorr_ret", "cofi_l1_z"
    ]
    
    # Analyze Premium Tier rejections
    if not prem_events.empty:
        # Fit model on training set
        from src.lighter_meta_labeler import purge_and_embargo_lighter
        prem_train_purged = purge_and_embargo_lighter(df_features, prem_events, 0, train_end, val_start, 0.05)
        prem_model = train_lighter_meta_labeler_v5(df_features, prem_train_purged)
        
        if prem_model is not None:
            # Feature Importances
            importances = prem_model.feature_importances_
            feat_imp = sorted(zip(FEATURE_COLS, importances), key=lambda x: x[1], reverse=True)
            print("\n--- PREMIUM META-LABELER FEATURE IMPORTANCE ---")
            for feat, val in feat_imp[:6]:
                print(f"  {feat:20s} : {val:.4f}")
                
            # Classify validation events
            val_events = prem_events[prem_events["entry_idx"] >= val_start].copy()
            
            executed_trades = []
            blocked_trades = []
            
            for idx, row in val_events.iterrows():
                feat_idx = int(row["signal_idx"])
                feats = np.array([[df_features.loc[feat_idx, col] for col in FEATURE_COLS]])
                prob = prem_model.predict_proba(feats)[0][1]
                
                # Premium tier cost parameters
                cost = 0.00004 + 0.00028 + 0.00002 if row["exit_type"] == "pt" else 0.00028 * 2 + 0.00002 * 2
                net_ret = row["raw_return"] - cost
                
                trade_info = {
                    **row,
                    "net_return": net_ret,
                    "prob": prob,
                    "feat_idx": feat_idx
                }
                
                if prob >= 0.5:
                    executed_trades.append(trade_info)
                else:
                    blocked_trades.append(trade_info)
                    
            exec_df = pd.DataFrame(executed_trades)
            block_df = pd.DataFrame(blocked_trades)
            
            print(f"\nPremium Validation Summary:")
            print(f"  Total Signals:   {len(val_events)}")
            print(f"  Executed Trades: {len(exec_df)}")
            print(f"  Blocked Trades:  {len(block_df)}")
            
            # Analyze features of Blocked vs Executed
            print("\n--- FEATURE COMPARISON (EXECUTED VS BLOCKED) ---")
            print(f"{'Feature':20s} | {'Executed Mean':15s} (std)  | {'Blocked Mean':15s} (std)")
            print("-" * 65)
            
            for col in ["avg_spread", "volatility_ratio", "tick_efficiency", "velocity", "cofi_l1_z"]:
                if len(exec_df) > 0:
                    exec_mean = df_features.loc[exec_df["feat_idx"], col].mean()
                    exec_std = df_features.loc[exec_df["feat_idx"], col].std()
                    exec_str = f"{exec_mean:.6f} ({exec_std:.6f})"
                else:
                    exec_str = "N/A"
                    
                if len(block_df) > 0:
                    block_mean = df_features.loc[block_df["feat_idx"], col].mean()
                    block_std = df_features.loc[block_df["feat_idx"], col].std()
                    block_str = f"{block_mean:.6f} ({block_std:.6f})"
                else:
                    block_str = "N/A"
                    
                print(f"{col:20s} | {exec_str:30s} | {block_str}")
                
            # Blocked Trades PnL Breakdown (Hypothetical)
            if len(block_df) > 0:
                block_wins = (block_df["net_return"] > 0).sum()
                block_losses = (block_df["net_return"] < 0).sum()
                block_total_ret = block_df["net_return"].sum()
                print(f"\nHypothetical PnL of blocked trades:")
                print(f"  Total Blocked Return: {block_total_ret * 100:+.4f}%")
                print(f"  Win / Loss Count:     {block_wins} wins / {block_losses} losses")
                print(f"  Win Rate if traded:   {block_wins / len(block_df) * 100:.2f}%")
                
            if len(exec_df) > 0:
                exec_wins = (exec_df["net_return"] > 0).sum()
                exec_losses = (exec_df["net_return"] < 0).sum()
                exec_total_ret = exec_df["net_return"].sum()
                print(f"\nExecuted Trades PnL:")
                print(f"  Total Executed Return: {exec_total_ret * 100:+.4f}%")
                print(f"  Win / Loss Count:      {exec_wins} wins / {exec_losses} losses")
                if len(exec_df) > 0:
                    print(f"  Win Rate:              {exec_wins / len(exec_df) * 100:.2f}%")
        else:
            print("Could not train Premium meta-labeler.")

if __name__ == "__main__":
    symbol = sys.argv[1].upper() if len(sys.argv) > 1 else "SOL"
    analyze_market_rejections(symbol)
