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
from src.lighter_meta_labeler import purge_and_embargo_lighter, train_lighter_meta_labeler

def evaluate_market(market_id, symbol):
    trades_file = f"data/raw_lighter_trades_{market_id}.jsonl"
    book_file = f"data/raw_lighter_book_{market_id}.jsonl"
    
    if not os.path.exists(trades_file) or not os.path.exists(book_file):
        print(f"Data files for {symbol} not found. Skipping...")
        return None
        
    print(f"\n=======================================================")
    print(f" PROCESSING MARKET: {symbol} (Market ID: {market_id})")
    print(f"=======================================================")
    
    # 1. Load trades
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
    print(f"Ingested {len(trades_df)} trades, total volume: {total_vol:.4f}")
    
    # 2. Build volume bars
    v_thresh = total_vol / 40
    bars_df = build_lighter_volume_bars(trades_file, v_thresh)
    print(f"Constructed {len(bars_df)} volume bars.")
    
    # 3. Map book updates to bars
    book_bar_mapping = map_lighter_book_updates_to_bars(book_file, bars_df)
    print(f"Mapped {len(book_bar_mapping)} book updates.")
    
    # 4. Compute enriched features
    df_features = compute_lighter_bar_features(bars_df, book_bar_mapping, trades, levels_count=5, z_window=10)
    
    # Reconstruct order book states for backtest lookup from already parsed mapping
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
    
    # 5. Apply triple barriers (using low z-threshold to ensure some trades are captured on short dataset)
    std_events = apply_lighter_triple_barriers(
        df_features, book_states, trade_events,
        pt_mult=2.0, sl_mult=1.0, hold_bars=5, z_threshold=0.1,
        latency_ms=300, maker_latency_ms=200
    )
    
    prem_events = apply_lighter_triple_barriers(
        df_features, book_states, trade_events,
        pt_mult=2.0, sl_mult=1.0, hold_bars=5, z_threshold=0.1,
        latency_ms=140, maker_latency_ms=0
    )
    
    print(f"Generated {len(std_events)} Standard events, {len(prem_events)} Premium events.")
    
    # 6. Train/Val Split and Meta-labeler
    n_bars = len(df_features)
    train_end = int(n_bars * 0.6)
    val_start = train_end + 1
    
    # Standard Model
    std_model = None
    if not std_events.empty:
        std_train_purged = purge_and_embargo_lighter(df_features, std_events, 0, train_end, val_start, 0.05)
        if len(std_train_purged) > 0:
            std_model = train_lighter_meta_labeler(df_features, std_train_purged)
            
    # Premium Model
    prem_model = None
    if not prem_events.empty:
        prem_train_purged = purge_and_embargo_lighter(df_features, prem_events, 0, train_end, val_start, 0.05)
        if len(prem_train_purged) > 0:
            prem_model = train_lighter_meta_labeler(df_features, prem_train_purged)
            
    # 7. Run Backtests
    std_val_events = std_events[std_events["entry_idx"] >= val_start].copy() if not std_events.empty else pd.DataFrame()
    prem_val_events = prem_events[prem_events["entry_idx"] >= val_start].copy() if not prem_events.empty else pd.DataFrame()
    
    # Standard (0% fee, 0.5 bps slippage)
    std_base = simulate_lighter_backtest(df_features, std_val_events, maker_fee=0.0, taker_fee=0.0, slippage=0.00005)
    std_meta = simulate_lighter_backtest(df_features, std_val_events, maker_fee=0.0, taker_fee=0.0, slippage=0.00005, meta_model=std_model, prob_thresh=0.5)
    
    # Premium (2.8 bps taker / 0.4 bps maker, 0.2 bps slippage)
    prem_base = simulate_lighter_backtest(df_features, prem_val_events, maker_fee=0.00004, taker_fee=0.00028, slippage=0.00002)
    prem_meta = simulate_lighter_backtest(df_features, prem_val_events, maker_fee=0.00004, taker_fee=0.00028, slippage=0.00002, meta_model=prem_model, prob_thresh=0.5)
    
    corr = df_features["cofi_z"].corr(df_features["next_ret"])
    print(f"OBI Z-score to Next Return Correlation: {corr:.4f}")
    
    return {
        "symbol": symbol,
        "correlation": corr,
        "std_base_return": std_base["metrics"]["total_return"] * 100,
        "std_base_trades": std_base["metrics"]["trade_count"],
        "std_meta_return": std_meta["metrics"]["total_return"] * 100,
        "std_meta_trades": std_meta["metrics"]["trade_count"],
        "prem_base_return": prem_base["metrics"]["total_return"] * 100,
        "prem_base_trades": prem_base["metrics"]["trade_count"],
        "prem_meta_return": prem_meta["metrics"]["total_return"] * 100,
        "prem_meta_trades": prem_meta["metrics"]["trade_count"]
    }

def main():
    markets = [
        (0, "ETH"),
        (1, "BTC"),
        (2, "SOL")
    ]
    
    results = []
    for mid, sym in markets:
        res = evaluate_market(mid, sym)
        if res:
            results.append(res)
            
    if not results:
        print("No market data evaluated.")
        return
        
    df = pd.DataFrame(results)
    
    print("\n" + "="*80)
    print("                    MULTI-PAIR EVALUATION SUMMARY")
    print("="*80)
    print(df.to_string(index=False))
    print("="*80)
    
    # Save to markdown report
    md_report = """# Multi-Pair Strategy Evaluation Report

This report compares the performance of the Order Book Imbalance (OBI) Scalper strategy across multiple pairs using enriched microstructural features.

## Side-by-Side Performance Comparison

| Pair | Correlation | Std Base PnL | Std Base Trades | Std Meta PnL | Std Meta Trades | Prem Base PnL | Prem Base Trades | Prem Meta PnL | Prem Meta Trades |
|------|-------------|--------------|-----------------|--------------|-----------------|---------------|------------------|---------------|------------------|
"""
    for r in results:
        md_report += f"| {r['symbol']} | {r['correlation']:.4f} | {r['std_base_return']:.4f}% | {r['std_base_trades']} | {r['std_meta_return']:.4f}% | {r['std_meta_trades']} | {r['prem_base_return']:.4f}% | {r['prem_base_trades']} | {r['prem_meta_return']:.4f}% | {r['prem_meta_trades']} |\n"
        
    report_path = "/root/.gemini/antigravity/brain/ce499ce1-b2b8-4fed-9913-698c063dcb39/multi_pair_evaluation.md"
    with open(report_path, "w") as f:
        f.write(md_report)
    print(f"\nWritten comparison report to: {report_path}")

if __name__ == "__main__":
    main()
