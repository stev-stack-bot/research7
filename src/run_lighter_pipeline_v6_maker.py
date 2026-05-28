import os
import sys
import glob
import io
import json
import numpy as np
import pandas as pd
from bisect import bisect_left
from sklearn.ensemble import RandomForestClassifier

# Add src to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.lighter_meta_labeler import purge_and_embargo_lighter
from src.run_lighter_pipeline_v3 import (
    stream_jsonl_zst, build_volume_bars_from_events,
    compute_bar_features_streaming
)

# 14 Optimized features
FEATURE_COLS = [
    "volatility_ratio",
    "kyle_lambda",
    "gini_coefficient",
    "ret_lag2",
    "tick_efficiency",
    "duration",
    "hurst",
    "amihud",
    "ret_lag1",
    "velocity",
    "avg_spread",
    "micro_ret",
    "autocorr_ret",
    "cofi_l1_z"
]

ASYMM_PARAMS = {
    "ETH": {
        "market_id": "0", "v_thresh": 78.4,
        "long": {"z_threshold": 1.5, "min_score": 3, "pt_mult": 1.0, "sl_mult": 1.0, "hold_bars": 5},
        "short": {"z_threshold": 1.0, "min_score": 2, "pt_mult": 5.0, "sl_mult": 2.0, "hold_bars": 10}
    },
    "BTC": {
        "market_id": "1", "v_thresh": 3.43,
        "long": {"z_threshold": 1.5, "min_score": 2, "pt_mult": 5.0, "sl_mult": 2.0, "hold_bars": 5},
        "short": {"z_threshold": 1.0, "min_score": 3, "pt_mult": 5.0, "sl_mult": 2.0, "hold_bars": 10}
    },
    "SOL": {
        "market_id": "2", "v_thresh": 513.8,
        "long": {"z_threshold": 1.5, "min_score": 2, "pt_mult": 2.0, "sl_mult": 1.0, "hold_bars": 10},
        "short": {"z_threshold": 1.0, "min_score": 2, "pt_mult": 5.0, "sl_mult": 2.0, "hold_bars": 10}
    }
}

def train_lighter_meta_labeler_v6(df, train_events):
    if train_events.empty:
        return None
        
    X_train = []
    y_train = []
    
    for idx, row in train_events.iterrows():
        feat_idx = int(row["signal_idx"])
        X_train.append([df.loc[feat_idx, col] for col in FEATURE_COLS])
        y_train.append(int(row["label"]))
        
    X_train = np.array(X_train)
    y_train = np.array(y_train)
    
    if len(np.unique(y_train)) < 2:
        return None
        
    model = RandomForestClassifier(n_estimators=100, max_depth=4, random_state=42)
    model.fit(X_train, y_train)
    return model

def simulate_lighter_backtest_v6(df, events_df, maker_fee=0.0, taker_fee=0.0, slippage=0.0, meta_model=None, prob_thresh=0.5):
    if events_df.empty:
        return {
            "pnl_df": pd.DataFrame(),
            "metrics": {
                "total_return": 0.0,
                "sharpe": 0.0,
                "drawdown": 0.0,
                "profit_factor": 0.0,
                "win_rate": 0.0,
                "trade_count": 0
            }
        }
        
    trades = []
    for idx, row in events_df.iterrows():
        feat_idx = int(row["signal_idx"])
        
        execute = True
        if meta_model is not None:
            features = np.array([[df.loc[feat_idx, col] for col in FEATURE_COLS]])
            prob_probs = meta_model.predict_proba(features)[0]
            prob = prob_probs[1] if len(prob_probs) > 1 else (1.0 if meta_model.classes_[0] == 1 else 0.0)
            if prob < prob_thresh:
                execute = False
                
        if execute:
            exit_type = row["exit_type"]
            # Entry is Maker order. Exit is Maker (if pt) or Taker (if sl/time).
            if exit_type == "pt":
                cost = maker_fee + maker_fee  # Maker entry + Maker exit, no slippage
            else:
                cost = maker_fee + taker_fee + slippage  # Maker entry + Taker exit + slippage
                
            net_return = row["raw_return"] - cost
            trades.append({
                "entry_idx": int(row["entry_idx"]),
                "signal_idx": feat_idx,
                "direction": row["direction"],
                "exit_type": exit_type,
                "raw_return": row["raw_return"],
                "net_return": net_return
            })
            
    if not trades:
        return {
            "pnl_df": pd.DataFrame(),
            "metrics": {
                "total_return": 0.0,
                "sharpe": 0.0,
                "drawdown": 0.0,
                "profit_factor": 0.0,
                "win_rate": 0.0,
                "trade_count": 0
            }
        }
        
    t_df = pd.DataFrame(trades)
    
    win_rate = (t_df["net_return"] > 0).mean()
    gross_gains = t_df[t_df["net_return"] > 0]["net_return"].sum()
    gross_losses = abs(t_df[t_df["net_return"] < 0]["net_return"].sum())
    profit_factor = gross_gains / gross_losses if gross_losses > 0 else float("inf")
    
    mean_ret = t_df["net_return"].mean()
    std_ret = t_df["net_return"].std()
    sharpe = (mean_ret / std_ret * np.sqrt(252 * 100)) if std_ret > 0 else 0.0
    
    t_df["cum_net_return"] = t_df["net_return"].cumsum()
    peak = t_df["cum_net_return"].cummax()
    drawdown = (peak - t_df["cum_net_return"]).max()
    
    metrics = {
        "total_return": float(t_df["net_return"].sum()),
        "sharpe": float(sharpe),
        "drawdown": float(drawdown),
        "profit_factor": float(profit_factor),
        "win_rate": float(win_rate),
        "trade_count": len(t_df)
    }
    
    return {
        "pnl_df": t_df,
        "metrics": metrics
    }

def apply_lighter_triple_barriers_v6(df, book_times, best_bids, best_asks, trade_events, asymm_params, latency_ms=300, maker_latency_ms=200, maker_fee=0.0, taker_fee=0.0, slippage=0.0):
    events = []
    trade_times = np.array([t["transaction_time"] for t in trade_events], dtype=np.int64)
    trade_prices = np.array([t["price"] for t in trade_events], dtype=np.float64)
    
    cofi_z_vals = df["cofi_z"].values
    micro_ret_vals = df["micro_ret"].values
    kyle_lambda_vals = df["kyle_lambda"].values
    depth_ratio_vals = df["depth_ratio"].values
    autocorr_vals = df["autocorr_ret"].values
    close_vals = df["close"].values
    
    # Calculate EMA(50) of close prices for macro trend filtering
    df_copy = df.copy()
    ema_trend = df_copy["close"].ewm(span=50, adjust=False).mean().values
    
    lp = asymm_params["long"]
    sp = asymm_params["short"]
    
    start_times = df["start_time"].values
    end_times = df["end_time"].values
    
    for idx, row in df.iterrows():
        cofi_z = cofi_z_vals[idx]
        micro_ret = micro_ret_vals[idx]
        kyle_lambda = kyle_lambda_vals[idx]
        depth_ratio = depth_ratio_vals[idx]
        autocorr = autocorr_vals[idx]
        close_px = close_vals[idx]
        trend_px = ema_trend[idx]
        
        # Check Long (aligned with trend: close_px > trend_px)
        score_long = 0
        if close_px > trend_px:
            if cofi_z >= lp["z_threshold"]:
                score_long += 1
            if micro_ret > 0:
                score_long += 1
            if kyle_lambda > 0:
                score_long += 1
            if depth_ratio > 1.0:
                score_long += 1
            if autocorr > 0:
                score_long += 1
                
        # Check Short (aligned with trend: close_px < trend_px)
        score_short = 0
        if close_px < trend_px:
            if cofi_z <= -sp["z_threshold"]:
                score_short += 1
            if micro_ret < 0:
                score_short += 1
            if kyle_lambda < 0:
                score_short += 1
            if depth_ratio < 1.0:
                score_short += 1
            if autocorr > 0:
                score_short += 1
            
        direction = 0
        pt_mult = 0.0
        sl_mult = 0.0
        hold_bars = 0
        
        if cofi_z >= lp["z_threshold"] and score_long >= lp["min_score"]:
            direction = 1
            pt_mult = lp["pt_mult"]
            sl_mult = lp["sl_mult"]
            hold_bars = lp["hold_bars"]
        elif cofi_z <= -sp["z_threshold"] and score_short >= sp["min_score"]:
            direction = -1
            pt_mult = sp["pt_mult"]
            sl_mult = sp["sl_mult"]
            hold_bars = sp["hold_bars"]
            
        if direction == 0:
            continue
            
        signal_time = row["end_time"]
        vol = row["volatility"]
        
        t_entry_exec = signal_time + latency_ms * 1000
        book_idx = np.searchsorted(book_times, t_entry_exec)
        if book_idx >= len(book_times):
            continue
            
        # PASSIVE LIMIT ENTRY: Place limit order at best bid (long) or best ask (short)
        limit_price = best_bids[book_idx] if direction == 1 else best_asks[book_idx]
        
        # Check fill probability: did subsequent trades touch or cross limit price?
        first_trade_idx = np.searchsorted(trade_times, t_entry_exec)
        filled = False
        t_fill = None
        
        # Allow order to sit in book for max 30 seconds
        t_cancel = t_entry_exec + 30 * 1000000
        
        for k in range(first_trade_idx, len(trade_times)):
            t_trade = trade_times[k]
            if t_trade > t_cancel:
                break
            p_trade = trade_prices[k]
            
            if direction == 1 and p_trade <= limit_price:
                filled = True
                t_fill = t_trade
                break
            elif direction == -1 and p_trade >= limit_price:
                filled = True
                t_fill = t_trade
                break
                
        if not filled:
            # Order canceled without fill
            continue
            
        # Find bar index of fill time
        fill_bar_idx_pos = np.searchsorted(start_times, t_fill, side='right') - 1
        if fill_bar_idx_pos >= 0 and t_fill <= end_times[fill_bar_idx_pos]:
            entry_idx = fill_bar_idx_pos
        else:
            entry_idx = idx
            
        # Entry price is exactly the limit price
        entry_price = limit_price
        
        pt_barrier = entry_price * (1 + pt_mult * vol * direction)
        sl_barrier = entry_price * (1 - sl_mult * vol * direction)
        
        t_maker_active = t_fill + maker_latency_ms * 1000
        expiry_bar_idx = min(entry_idx + hold_bars, len(df) - 1)
        t_expiry = df.loc[expiry_bar_idx, "end_time"]
        
        first_exit_trade_idx = np.searchsorted(trade_times, t_fill)
        exit_time = t_expiry
        exit_type = "time"
        
        for k in range(first_exit_trade_idx, len(trade_times)):
            t_trade = trade_times[k]
            if t_trade > t_expiry:
                break
            p_trade = trade_prices[k]
            
            # SL is Taker trigger
            if direction == 1 and p_trade <= sl_barrier:
                exit_time = t_trade
                exit_type = "sl"
                break
            elif direction == -1 and p_trade >= sl_barrier:
                exit_time = t_trade
                exit_type = "sl"
                break
                
            # PT is Maker order
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
        
        # Calculate cost dynamically to determine net return label
        if exit_type == "pt":
            cost = maker_fee + maker_fee
        else:
            cost = maker_fee + taker_fee + slippage
            
        net_ret = raw_ret - cost
        label = 1 if net_ret > 0.0 else 0
        
        events.append({
            "entry_idx": entry_idx,
            "signal_idx": idx,
            "entry_time": t_fill,
            "direction": direction,
            "exit_idx": exit_idx,
            "exit_time": exit_time,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "exit_type": exit_type,
            "raw_return": raw_ret,
            "label": label
        })
        
    return pd.DataFrame(events)

def run_market_backtest_v6(symbol):
    asym_params = ASYMM_PARAMS[symbol]
    mid = asym_params["market_id"]
    
    data_dir = "data"
    trade_files = sorted(glob.glob(os.path.join(data_dir, f"raw_lighter_trades_{mid}_*.jsonl.zst")))
    book_files = sorted(glob.glob(os.path.join(data_dir, f"raw_lighter_book_{mid}_*.jsonl.zst")))
    
    if not trade_files or not book_files:
        print(f"\nNo data files found for market {symbol}. Skipping...")
        return None
        
    print(f"\n=======================================================")
    print(f" PROCESSING MARKET (MAKER ENTRY): {symbol} (Market ID: {mid})")
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
    
    v_thresh = asym_params["v_thresh"]
    
    # 2. Build volume bars
    bars_df = build_volume_bars_from_events(trades, v_thresh)
    
    # 3 & 4. Map books and compute features
    df_features, book_times, best_bids, best_asks = compute_bar_features_streaming(
        bars_df, book_files, trades, z_window=100
    )
    
    # 5. Apply Passive Maker Exits
    print("Applying Asymmetric Triple Barrier Method exits (Maker Entries)...")
    # Standard: 300ms latency, 0% fees, 0.5 bps slippage (only on taker exits)
    std_events = apply_lighter_triple_barriers_v6(
        df_features, book_times, best_bids, best_asks, trades,
        asymm_params=asym_params, latency_ms=300, maker_latency_ms=200,
        maker_fee=0.0, taker_fee=0.0, slippage=0.00005
    )
    
    # Premium: 140ms latency, 0.4 bps maker fee, 2.8 bps taker fee, 0.2 bps slippage (on taker exits)
    prem_events = apply_lighter_triple_barriers_v6(
        df_features, book_times, best_bids, best_asks, trades,
        asymm_params=asym_params, latency_ms=140, maker_latency_ms=0,
        maker_fee=0.00004, taker_fee=0.00028, slippage=0.00002
    )
    
    print(f"Standard Tier: Generated {len(std_events)} events.")
    print(f"Premium Tier: Generated {len(prem_events)} events.")
    
    # 6. Splitting Data and training models
    n_bars = len(df_features)
    train_end = int(n_bars * 0.6)
    val_start = train_end + 1
    
    std_model = None
    if not std_events.empty:
        std_train_purged = purge_and_embargo_lighter(df_features, std_events, 0, train_end, val_start, 0.05)
        if len(std_train_purged) > 0:
            std_model = train_lighter_meta_labeler_v6(df_features, std_train_purged)
            
    prem_model = None
    if not prem_events.empty:
        prem_train_purged = purge_and_embargo_lighter(df_features, prem_events, 0, train_end, val_start, 0.05)
        if len(prem_train_purged) > 0:
            prem_model = train_lighter_meta_labeler_v6(df_features, prem_train_purged)
            
    std_val_events = std_events[std_events["entry_idx"] >= val_start].copy() if not std_events.empty else pd.DataFrame()
    prem_val_events = prem_events[prem_events["entry_idx"] >= val_start].copy() if not prem_events.empty else pd.DataFrame()
    
    # 7. Run Backtests
    std_baseline_res = simulate_lighter_backtest_v6(df_features, std_val_events, maker_fee=0.0, taker_fee=0.0, slippage=0.00005)
    std_meta_res = simulate_lighter_backtest_v6(df_features, std_val_events, maker_fee=0.0, taker_fee=0.0, slippage=0.00005, meta_model=std_model, prob_thresh=0.5)
    
    prem_baseline_res = simulate_lighter_backtest_v6(df_features, prem_val_events, maker_fee=0.00004, taker_fee=0.00028, slippage=0.00002)
    prem_meta_res = simulate_lighter_backtest_v6(df_features, prem_val_events, maker_fee=0.00004, taker_fee=0.00028, slippage=0.00002, meta_model=prem_model, prob_thresh=0.5)
    
    test_bars = df_features[df_features["bar_index"] >= val_start]
    if not test_bars.empty and len(test_bars) > 1:
        bench_ret = (test_bars.iloc[-1]["close"] - test_bars.iloc[0]["close"]) / test_bars.iloc[0]["close"]
    else:
        bench_ret = 0.0
        
    print("\n=======================================================")
    print(f"            LIGHTER PERFORMANCE (MAKER ENTRY) ({symbol})")
    print("=======================================================")
    print(f"Benchmark Buy-and-Hold Return: {bench_ret * 100:.4f}%")
    print("-------------------------------------------------------")
    print("STANDARD TIER:")
    print(f"  - Baseline:   {std_baseline_res['metrics']['total_return']*100:+.4f}% | PF: {std_baseline_res['metrics']['profit_factor']:.2f} | Sharpe: {std_baseline_res['metrics']['sharpe']:.2f} | Trades: {std_baseline_res['metrics']['trade_count']}")
    print(f"  - Meta-Label: {std_meta_res['metrics']['total_return']*100:+.4f}% | PF: {std_meta_res['metrics']['profit_factor']:.2f} | Sharpe: {std_meta_res['metrics']['sharpe']:.2f} | Trades: {std_meta_res['metrics']['trade_count']}")
    print("-------------------------------------------------------")
    print("PREMIUM TIER:")
    print(f"  - Baseline:   {prem_baseline_res['metrics']['total_return']*100:+.4f}% | PF: {prem_baseline_res['metrics']['profit_factor']:.2f} | Sharpe: {prem_baseline_res['metrics']['sharpe']:.2f} | Trades: {prem_baseline_res['metrics']['trade_count']}")
    print(f"  - Meta-Label: {prem_meta_res['metrics']['total_return']*100:+.4f}% | PF: {prem_meta_res['metrics']['profit_factor']:.2f} | Sharpe: {prem_meta_res['metrics']['sharpe']:.2f} | Trades: {prem_meta_res['metrics']['trade_count']}")
    print("=======================================================")
    
    return {
        "symbol": symbol,
        "bench_ret": bench_ret,
        "std_baseline": std_baseline_res["metrics"],
        "std_meta": std_meta_res["metrics"],
        "prem_baseline": prem_baseline_res["metrics"],
        "prem_meta": prem_meta_res["metrics"]
    }

def main():
    market_arg = sys.argv[1].upper() if len(sys.argv) > 1 else "ALL"
    
    if market_arg == "ALL":
        symbols = ["ETH", "BTC", "SOL"]
    elif market_arg in ASYMM_PARAMS:
        symbols = [market_arg]
    else:
        print(f"Invalid market argument: {market_arg}.")
        return
        
    results = {}
    for sym in symbols:
        res = run_market_backtest_v6(sym)
        if res:
            results[sym] = res
            
    if results:
        md_report = """# Passive Maker Entry Backtesting Report (V6)

This report presents backtesting results where the strategy posts passive maker limit orders at the bid/ask and checks subsequent market trade events to model fill probability.

## Performance Summary Table

| Pair | Benchmark Return | Std Base Return | Std Base Sharpe | Std Meta Return | Std Meta Sharpe | Prem Base Return | Prem Base Sharpe | Prem Meta Return | Prem Meta Sharpe |
|------|------------------|-----------------|-----------------|-----------------|-----------------|------------------|------------------|------------------|------------------|
"""
        for sym, r in results.items():
            b_ret = r["bench_ret"] * 100
            
            std_base_ret = r["std_baseline"]["total_return"] * 100
            std_base_sh  = r["std_baseline"]["sharpe"]
            std_meta_ret = r["std_meta"]["total_return"] * 100
            std_meta_sh  = r["std_meta"]["sharpe"]
            
            prem_base_ret = r["prem_baseline"]["total_return"] * 100
            prem_base_sh  = r["prem_baseline"]["sharpe"]
            prem_meta_ret = r["prem_meta"]["total_return"] * 100
            prem_meta_sh  = r["prem_meta"]["sharpe"]
            
            md_report += f"| {sym} | {b_ret:.4f}% | {std_base_ret:+.4f}% | {std_base_sh:.2f} | {std_meta_ret:+.4f}% | {std_meta_sh:.2f} | {prem_base_ret:+.4f}% | {prem_base_sh:.2f} | {prem_meta_ret:+.4f}% | {prem_meta_sh:.2f} |\n"
            
        report_path = "/kaggle/research7/multi_pair_61h_report_v6.md"
        with open(report_path, "w") as f:
            f.write(md_report)
        print(f"\nWritten V6 Maker summary report to: {report_path}")

        # Also write JSON of all results
        with open("/kaggle/research7/data/v6_maker_scorecard.json", "w") as f:
            json.dump(results, f, indent=4)

if __name__ == "__main__":
    main()
