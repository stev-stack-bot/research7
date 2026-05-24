import os
import sys
import json
import numpy as np
import pandas as pd
from scipy import stats

# Add src to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.lighter_bars import build_lighter_volume_bars, map_lighter_book_updates_to_bars
from src.lighter_features import compute_lighter_bar_features
from src.lighter_backtester import apply_lighter_triple_barriers, simulate_lighter_backtest

def main():
    trades_file = "data/raw_lighter_trades_0.jsonl"
    book_file = "data/raw_lighter_book_0.jsonl"
    
    if not os.path.exists(trades_file) or not os.path.exists(book_file):
        print("Data files not found. Run recorder first.")
        return
        
    print("=======================================================")
    print("          QUANTITATIVE VALIDATION PIPELINE             ")
    print("=======================================================")
    
    # 1. Load data & construct bars
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
    v_thresh = total_vol / 40
    
    bars_df = build_lighter_volume_bars(trades_file, v_thresh)
    book_bar_mapping = map_lighter_book_updates_to_bars(book_file, bars_df)
    df_features = compute_lighter_bar_features(bars_df, book_bar_mapping, trades, levels_count=5, z_window=10)

    
    # Reconstruct order book states for lookups
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
    
    # 2. Target Leakage Validation
    print("\n[GATE 1] TARGET LEAKAGE CHECK:")
    leak_detected = False
    for idx, row in df_features.iterrows():
        if idx < len(df_features) - 1:
            actual_next_close = df_features.loc[idx+1, "close"]
            actual_curr_close = df_features.loc[idx, "close"]
            expected_next_ret = np.log(actual_next_close / actual_curr_close)
            if not np.isclose(row["next_ret"], expected_next_ret):
                print(f"  - Target Return Leakage Detected at index {idx}!")
                leak_detected = True
    if not leak_detected:
        print("  - PASS: next_ret is strictly computed using only close_{t+1}/close_t and does not leak future data.")
        
    # Check correlation between features (e.g. cofi_z) and next_ret
    corr = df_features["cofi_z"].corr(df_features["next_ret"])
    print(f"  - Correlation between OBI Z-score and Next Return: {corr:.4f}")
    
    # 3. Bar Stability & Statistical Properties
    print("\n[GATE 2] BAR STABILITY & STATISTICAL PROPERTIES:")
    # Build time-based bars of equal intervals
    t_min = trades_df["transaction_time"].min()
    t_max = trades_df["transaction_time"].max()
    t_step = (t_max - t_min) / 10
    
    time_bars = []
    for i in range(10):
        t_start = t_min + i * t_step
        t_end = t_start + t_step
        sub_trades = trades_df[(trades_df["transaction_time"] >= t_start) & (trades_df["transaction_time"] < t_end)]
        if not sub_trades.empty:
            time_bars.append({
                "open": sub_trades.iloc[0]["price"],
                "high": sub_trades["price"].max(),
                "low": sub_trades["price"].min(),
                "close": sub_trades.iloc[-1]["price"],
                "volume": sub_trades["size"].sum()
            })
        else:
            prev_close = time_bars[-1]["close"] if time_bars else trades_df.iloc[0]["price"]
            time_bars.append({
                "open": prev_close, "high": prev_close, "low": prev_close, "close": prev_close, "volume": 0.0
            })
    time_bars_df = pd.DataFrame(time_bars)
    
    vol_returns = df_features["ret"].values
    time_returns = np.log(time_bars_df["close"] / time_bars_df["close"].shift(1)).fillna(0.0).values
    
    # Test for normality using Jarque-Bera
    jb_vol_stat, jb_vol_p = stats.jarque_bera(vol_returns) if len(vol_returns) >= 3 else (0.0, 1.0)
    jb_time_stat, jb_time_p = stats.jarque_bera(time_returns) if len(time_returns) >= 3 else (0.0, 1.0)
    
    print(f"  - Volume Bars Returns - JB p-value: {jb_vol_p:.4f} (stat={jb_vol_stat:.4f})")
    print(f"  - Time Bars Returns - JB p-value: {jb_time_p:.4f} (stat={jb_time_stat:.4f})")
    print(f"  - Volume Bars Return Skewness: {stats.skew(vol_returns):.4f}, Kurtosis: {stats.kurtosis(vol_returns):.4f}")
    print(f"  - Time Bars Return Skewness: {stats.skew(time_returns):.4f}, Kurtosis: {stats.kurtosis(time_returns):.4f}")
    
    # 4. Cost/Slippage Sensitivity
    print("\n[GATE 3] COST & SLIPPAGE SENSITIVITY:")
    std_events = apply_lighter_triple_barriers(df_features, book_states, trade_events, pt_mult=2.0, sl_mult=1.0, hold_bars=5, z_threshold=0.01, latency_ms=300, maker_latency_ms=200)
    
    print("  - Evaluating Standard Account Strategy across slippage levels:")
    for slip in [0.0, 0.00005, 0.0001, 0.0002, 0.0005]:
        res = simulate_lighter_backtest(df_features, std_events, maker_fee=0.0, taker_fee=0.0, slippage=slip)
        tot_ret = res["metrics"]["total_return"] * 100
        print(f"    * Slippage: {slip*10000:.1f} bps | Total Return: {tot_ret:.4f}% | Trades: {res['metrics']['trade_count']}")
        
    prem_events = apply_lighter_triple_barriers(df_features, book_states, trade_events, pt_mult=2.0, sl_mult=1.0, hold_bars=5, z_threshold=0.01, latency_ms=140, maker_latency_ms=0)
    print("  - Evaluating Premium Account Strategy across slippage levels:")
    for slip in [0.0, 0.00002, 0.00005, 0.0001, 0.0002]:
        res = simulate_lighter_backtest(df_features, prem_events, maker_fee=0.00004, taker_fee=0.00028, slippage=slip)
        tot_ret = res["metrics"]["total_return"] * 100
        print(f"    * Slippage: {slip*10000:.1f} bps | Total Return: {tot_ret:.4f}% | Trades: {res['metrics']['trade_count']}")
        
    # 5. Liquidity/Capacity Verification
    print("\n[GATE 4] LIQUIDITY & CAPACITY CHECKS:")
    avg_bid_depth = np.mean([sum(level["sz"] for level in state["bids"][:3]) for state in book_states if state["bids"]])
    avg_ask_depth = np.mean([sum(level["sz"] for level in state["asks"][:3]) for state in book_states if state["asks"]])
    avg_trade_sz = trades_df["size"].mean()
    
    print(f"  - Average Bid Depth (Top 3 levels): {avg_bid_depth:.4f} ETH")
    print(f"  - Average Ask Depth (Top 3 levels): {avg_ask_depth:.4f} ETH")
    print(f"  - Average Trade Size: {avg_trade_sz:.4f} ETH")
    capacity_ratio = (avg_bid_depth + avg_ask_depth) / 2.0 / avg_trade_sz if avg_trade_sz > 0 else 0.0
    print(f"  - Order Book Capacity to Trade Size Ratio: {capacity_ratio:.1f}x")
    
    print("\nValidation pipeline execution complete.")

if __name__ == "__main__":
    main()
