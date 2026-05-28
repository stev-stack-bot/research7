import os
import sys
import glob
import io
import json
import numpy as np
import pandas as pd
from bisect import bisect_left
from sklearn.ensemble import RandomForestClassifier

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.lighter_meta_labeler import purge_and_embargo_lighter
from src.run_lighter_pipeline_v3 import stream_jsonl_zst, build_volume_bars_from_events, compute_ofi_delta

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

TICK_SIZES = {
    "ETH": 0.01,
    "BTC": 0.1,
    "SOL": 0.001
}

def compute_bar_features_streaming_v8(bars_df, book_files, trades, z_window=100):
    bar_starts = bars_df["start_time"].values
    bar_ends = bars_df["end_time"].values
    max_bar_idx = len(bars_df) - 1
    max_bar_end = bar_ends[-1]
    
    n_bars = len(bars_df)
    bar_cofi = np.zeros(n_bars)
    bar_cofi_l1 = np.zeros(n_bars)
    bar_spread_sum = np.zeros(n_bars)
    bar_spread_count = np.zeros(n_bars)
    bar_last_levels = [None] * n_bars
    bar_prev_levels = [None] * n_bars
    
    book_times_list = []
    best_bids_list = []
    best_asks_list = []
    best_bid_szs_list = []
    best_ask_szs_list = []
    
    current_bids = {}
    current_asks = {}
    
    print("Streaming book updates to calculate features and track L1 sizes...")
    update_count = 0
    for msg in stream_jsonl_zst(book_files):
        ob_data = msg.get("order_book", {})
        if not ob_data:
            continue
        
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
        
        if not current_bids or not current_asks:
            continue
            
        if update_count % 500 == 0:
            best_bid = max(current_bids.keys())
            best_ask = min(current_asks.keys())
            mid_px = (best_bid + best_ask) / 2.0
            
            for px in list(current_bids.keys()):
                if px < mid_px * 0.95:
                    current_bids.pop(px)
            for px in list(current_asks.keys()):
                if px > mid_px * 1.05:
                    current_asks.pop(px)
        
        sorted_bid_keys = sorted(current_bids.keys(), reverse=True)[:5]
        sorted_bids = [{"px": p, "sz": current_bids[p]} for p in sorted_bid_keys]
        
        sorted_ask_keys = sorted(current_asks.keys())[:5]
        sorted_asks = [{"px": p, "sz": current_asks[p]} for p in sorted_ask_keys]
        
        ts_us = int(ob_data.get("last_updated_at") or msg.get("last_updated_at"))
        
        book_times_list.append(ts_us)
        best_bids_list.append(sorted_bids[0]["px"])
        best_asks_list.append(sorted_asks[0]["px"])
        best_bid_szs_list.append(sorted_bids[0]["sz"])
        best_ask_szs_list.append(sorted_asks[0]["sz"])
        
        pos = np.searchsorted(bar_starts, ts_us, side='right') - 1
        bar_idx = None
        if pos >= 0:
            if ts_us <= bar_ends[pos]:
                bar_idx = pos
            elif ts_us > max_bar_end:
                bar_idx = max_bar_idx
        else:
            if ts_us > max_bar_end:
                bar_idx = max_bar_idx
                 
        if bar_idx is not None:
            levels = [sorted_bids, sorted_asks]
            if bar_prev_levels[bar_idx] is None:
                bar_prev_levels[bar_idx] = levels
            else:
                delta = compute_ofi_delta(bar_prev_levels[bar_idx], levels, levels_count=5)
                delta_l1 = compute_ofi_delta(bar_prev_levels[bar_idx], levels, levels_count=1)
                bar_cofi[bar_idx] += delta
                bar_cofi_l1[bar_idx] += delta_l1
                bar_prev_levels[bar_idx] = levels
                
            spread = sorted_asks[0]["px"] - sorted_bids[0]["px"]
            bar_spread_sum[bar_idx] += spread
            bar_spread_count[bar_idx] += 1
            bar_last_levels[bar_idx] = levels
            
        update_count += 1
        if update_count % 200000 == 0:
            print(f"  Processed {update_count} book updates...")
            
    print(f"Processed a total of {update_count} book updates.")
    
    book_times = np.array(book_times_list, dtype=np.int64)
    best_bids = np.array(best_bids_list, dtype=np.float64)
    best_asks = np.array(best_asks_list, dtype=np.float64)
    best_bid_szs = np.array(best_bid_szs_list, dtype=np.float64)
    best_ask_szs = np.array(best_ask_szs_list, dtype=np.float64)
    
    # Calculate final features per bar
    cofi_values = []
    cofi_l1_values = []
    avg_spread_values = []
    micro_prices = []
    depth_ratio_l3 = []
    depth_ratio_l5 = []
    depth_ratio = []
    bid_prices = []
    ask_prices = []
    
    last_spread = 0.0
    last_p_micro = None
    
    for idx, row in bars_df.iterrows():
        bar_idx = int(row["bar_index"])
        cofi_values.append(bar_cofi[bar_idx])
        cofi_l1_values.append(bar_cofi_l1[bar_idx])
        
        if bar_spread_count[bar_idx] > 0:
            last_spread = bar_spread_sum[bar_idx] / bar_spread_count[bar_idx]
        avg_spread_values.append(last_spread)
        
        last_levels = bar_last_levels[bar_idx]
        if last_levels is None:
            micro_prices.append(last_p_micro if last_p_micro is not None else row["close"])
            depth_ratio_l3.append(1.0)
            depth_ratio_l5.append(1.0)
            depth_ratio.append(1.0)
            bid_prices.append(row["close"])
            ask_prices.append(row["close"])
        else:
            bid_px = float(last_levels[0][0]["px"])
            bid_sz = float(last_levels[0][0]["sz"])
            ask_px = float(last_levels[1][0]["px"])
            ask_sz = float(last_levels[1][0]["sz"])
            
            if bid_sz + ask_sz > 0:
                last_p_micro = (bid_px * ask_sz + ask_px * bid_sz) / (bid_sz + ask_sz)
            else:
                last_p_micro = row["close"]
            micro_prices.append(last_p_micro)
            
            try:
                bids_l3 = sum(float(b["sz"]) for b in last_levels[0][:3])
                asks_l3 = sum(float(a["sz"]) for a in last_levels[1][:3])
                depth_ratio_l3.append(bids_l3 / asks_l3 if asks_l3 > 0 else 1.0)
            except Exception:
                depth_ratio_l3.append(1.0)
                
            try:
                bids_l5 = sum(float(b["sz"]) for b in last_levels[0][:5])
                asks_l5 = sum(float(a["sz"]) for a in last_levels[1][:5])
                depth_ratio_l5.append(bids_l5 / asks_l5 if asks_l5 > 0 else 1.0)
            except Exception:
                depth_ratio_l5.append(1.0)
                
            depth_ratio.append(bid_sz / ask_sz if ask_sz > 0 else 1.0)
            bid_prices.append(bid_px)
            ask_prices.append(ask_px)
            
    bars_df["cofi"] = cofi_values
    bars_df["cofi_l1"] = cofi_l1_values
    bars_df["avg_spread"] = avg_spread_values
    bars_df["micro_price"] = micro_prices
    bars_df["depth_ratio_l3"] = depth_ratio_l3
    bars_df["depth_ratio_l5"] = depth_ratio_l5
    bars_df["depth_ratio"] = depth_ratio
    bars_df["bid"] = bid_prices
    bars_df["ask"] = ask_prices
    
    rolling_mean = bars_df["cofi"].rolling(window=z_window, min_periods=1).mean()
    rolling_std = bars_df["cofi"].rolling(window=z_window, min_periods=1).std().fillna(1.0)
    bars_df["cofi_z"] = (bars_df["cofi"] - rolling_mean) / rolling_std
    
    rolling_mean_l1 = bars_df["cofi_l1"].rolling(window=z_window, min_periods=1).mean()
    rolling_std_l1 = bars_df["cofi_l1"].rolling(window=z_window, min_periods=1).std().fillna(1.0)
    bars_df["cofi_l1_z"] = (bars_df["cofi_l1"] - rolling_mean_l1) / rolling_std_l1
    
    bars_df["ret"] = np.log(bars_df["close"] / bars_df["close"].shift(1)).fillna(0.0)
    bars_df["micro_ret"] = np.log(bars_df["micro_price"] / bars_df["micro_price"].shift(1)).fillna(0.0)
    
    bars_df["volatility"] = bars_df["ret"].rolling(window=z_window, min_periods=1).std().fillna(0.0001)
    bars_df["volatility_ratio"] = (
        bars_df["ret"].rolling(window=10, min_periods=1).std() / 
        bars_df["volatility"]
    ).fillna(1.0)
    
    bars_df["duration"] = (bars_df["end_time"] - bars_df["start_time"]) / 1000000.0
    
    bars_df["ret_lag1"] = bars_df["ret"].shift(1).fillna(0.0)
    bars_df["ret_lag2"] = bars_df["ret"].shift(2).fillna(0.0)
    
    bar_to_trades = {i: [] for i in range(n_bars)}
    for t in trades:
        t_time = t["transaction_time"]
        pos = np.searchsorted(bar_starts, t_time, side='right') - 1
        if pos >= 0 and t_time <= bar_ends[pos]:
            bar_to_trades[pos].append(t)
        elif pos >= 0 and t_time > max_bar_end:
            bar_to_trades[max_bar_idx].append(t)
            
    vpin_values = []
    gini_values = []
    tick_efficiency_values = []
    signed_vol_values = []
    
    for bar_idx in range(n_bars):
        bar_trades = bar_to_trades[bar_idx]
        if not bar_trades:
            vpin_values.append(0.0)
            gini_values.append(0.0)
            tick_efficiency_values.append(1.0)
            signed_vol_values.append(0.0)
            continue
            
        buy_vol = 0.0
        sell_vol = 0.0
        total_vol = 0.0
        
        for trade in bar_trades:
            p_trade = trade["price"]
            sz_trade = trade["size"]
            t_trade = trade["transaction_time"]
            
            if len(book_times) > 0:
                book_idx = np.searchsorted(book_times, t_trade)
                if book_idx >= len(book_times):
                    book_idx = len(book_times) - 1
                mid_px = (best_bids[book_idx] + best_asks[book_idx]) / 2.0
            else:
                mid_px = p_trade
                
            if p_trade >= mid_px:
                buy_vol += sz_trade
            else:
                sell_vol += sz_trade
            total_vol += sz_trade
            
        vpin_values.append(abs(buy_vol - sell_vol) / total_vol if total_vol > 0 else 0.0)
        signed_vol_values.append(buy_vol - sell_vol)
        
        sizes = [t["size"] for t in bar_trades]
        if len(sizes) <= 1:
            gini_values.append(0.0)
        else:
            sorted_sizes = np.sort(sizes)
            n = len(sorted_sizes)
            coef = 2.0 / n
            const = (n + 1.0) / n
            weighted_sum = sum((i + 1) * val for i, val in enumerate(sorted_sizes))
            sum_sizes = sum(sorted_sizes)
            gini_val = (coef * weighted_sum / sum_sizes - const) if sum_sizes > 0 else 0.0
            gini_values.append(gini_val)
            
        prices = [t["price"] for t in bar_trades]
        if len(prices) <= 1:
            tick_efficiency_values.append(1.0)
        else:
            net_disp = abs(prices[-1] - prices[0])
            tot_path = sum(abs(prices[i] - prices[i-1]) for i in range(1, len(prices)))
            efficiency_val = net_disp / tot_path if tot_path > 0 else 1.0
            tick_efficiency_values.append(efficiency_val)
            
    bars_df["vpin"] = vpin_values
    bars_df["gini_coefficient"] = gini_values
    bars_df["tick_efficiency"] = tick_efficiency_values
    bars_df["signed_volume"] = signed_vol_values
    
    bars_df["velocity"] = bars_df.apply(
        lambda r: r["volume"] / r["duration"] if r["duration"] > 0 else 0.0, axis=1
    )
    
    # 1. Kyle's Lambda (rolling price impact)
    bars_df["price_diff"] = bars_df["close"].diff().fillna(0.0)
    roll_cov = bars_df["price_diff"].rolling(window=20, min_periods=5).cov(bars_df["signed_volume"])
    roll_var = bars_df["signed_volume"].rolling(window=20, min_periods=5).var().fillna(1.0)
    bars_df["kyle_lambda"] = (roll_cov / roll_var).fillna(0.0)
    
    # 2. Autocorrelation of returns
    bars_df["autocorr_ret"] = bars_df["ret"].rolling(window=20, min_periods=5).apply(
        lambda x: x.autocorr(lag=1) if len(x) >= 5 else 0.0, raw=False
    ).fillna(0.0)
    
    # 3. Amihud Illiquidity Ratio
    bars_df["amihud"] = (bars_df["ret"].abs() / (bars_df["volume"] + 1e-8)).rolling(window=20, min_periods=1).mean().fillna(0.0)
    
    # 4. Hurst Exponent proxy
    def hurst_chunk(x):
        if len(x) < 5:
            return 0.5
        centered = x - np.mean(x)
        cum_dev = np.cumsum(centered)
        R = np.max(cum_dev) - np.min(cum_dev)
        S = np.std(x)
        if S > 1e-12 and R > 1e-12:
            H = np.log(R / S) / np.log(len(x))
            return np.clip(H, 0.0, 1.0)
        return 0.5
    bars_df["hurst"] = bars_df["close"].rolling(window=20, min_periods=5).apply(hurst_chunk, raw=True).fillna(0.5)
    
    # 5. Volume clock acceleration
    duration_ema = bars_df["duration"].ewm(span=20, min_periods=1).mean()
    bars_df["volume_accel"] = (duration_ema / (bars_df["duration"] + 1e-6)).fillna(1.0)
    
    # 6. Spread z-score
    spread_mean = bars_df["avg_spread"].rolling(window=100, min_periods=1).mean()
    spread_std = bars_df["avg_spread"].rolling(window=100, min_periods=1).std().fillna(1.0)
    bars_df["spread_z"] = ((bars_df["avg_spread"] - spread_mean) / spread_std).fillna(0.0)

    # Normalized velocity mean and std for Z-score checks
    bars_df["velocity_mean"] = bars_df["velocity"].rolling(window=100, min_periods=10).mean().fillna(bars_df["velocity"])
    bars_df["velocity_std"] = bars_df["velocity"].rolling(window=100, min_periods=10).std().fillna(1.0)
    
    return bars_df, book_times, best_bids, best_asks, best_bid_szs, best_ask_szs

def apply_lighter_triple_barriers_v8(symbol, df, book_times, best_bids, best_asks, best_bid_szs, best_ask_szs, trade_events, asymm_params, latency_ms=300, maker_latency_ms=200, maker_fee=0.0, taker_fee=0.0, slippage=0.0):
    events = []
    trade_times = np.array([t["transaction_time"] for t in trade_events], dtype=np.int64)
    trade_prices = np.array([t["price"] for t in trade_events], dtype=np.float64)
    trade_sizes = np.array([t["size"] for t in trade_events], dtype=np.float64)
    
    cofi_z_vals = df["cofi_z"].values
    micro_ret_vals = df["micro_ret"].values
    kyle_lambda_vals = df["kyle_lambda"].values
    depth_ratio_vals = df["depth_ratio"].values
    autocorr_vals = df["autocorr_ret"].values
    close_vals = df["close"].values
    velocity_vals = df["velocity"].values
    velocity_mean_vals = df["velocity_mean"].values
    velocity_std_vals = df["velocity_std"].values
    
    # EMA(50) of close prices for macro trend filtering
    df_copy = df.copy()
    ema_trend = df_copy["close"].ewm(span=50, adjust=False).mean().values
    
    lp = asymm_params["long"]
    sp = asymm_params["short"]
    
    start_times = df["start_time"].values
    end_times = df["end_time"].values
    tick_size = TICK_SIZES[symbol]
    
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
            
        # AGGRESSIVE QUEUE FRONT-RUNNING LOGIC:
        best_bid = best_bids[book_idx]
        best_ask = best_asks[book_idx]
        spread = best_ask - best_bid
        
        if direction == 1:
            if spread > tick_size * 1.001:  # Enforce strictly greater than 1 tick spread
                limit_price = best_bid + tick_size
                resting_size = 0.0  # Jumps to front of queue (no touch penalty)
            else:
                limit_price = best_bid
                resting_size = best_bid_szs[book_idx]
        else:
            if spread > tick_size * 1.001:
                limit_price = best_ask - tick_size
                resting_size = 0.0
            else:
                limit_price = best_ask
                resting_size = best_ask_szs[book_idx]
                
        # Check fill probability with Touch Volume clearance and Post-Only Pull (rolling Z-score)
        first_trade_idx = np.searchsorted(trade_times, t_entry_exec)
        filled = False
        t_fill = None
        cum_vol_at_limit = 0.0
        
        # Allow order to sit in book for max 30 seconds
        t_cancel = t_entry_exec + 30 * 1000000
        
        for k in range(first_trade_idx, len(trade_times)):
            t_trade = trade_times[k]
            if t_trade > t_cancel:
                break
            p_trade = trade_prices[k]
            sz_trade = trade_sizes[k]
            
            # Post-Only Pull Signal (Heuristic 2):
            # Check the bar index of this trade
            trade_bar_idx_pos = np.searchsorted(start_times, t_trade, side='right') - 1
            current_bar_idx = max(idx, trade_bar_idx_pos) if trade_bar_idx_pos >= 0 else idx
            
            curr_velocity = velocity_vals[current_bar_idx]
            v_mean = velocity_mean_vals[current_bar_idx]
            v_std = velocity_std_vals[current_bar_idx]
            
            # Pull order if velocity exceeds 2.5 standard deviations (normalized toxic flow detector)
            z_velocity = (curr_velocity - v_mean) / (v_std + 1e-6)
            if z_velocity > 2.5:
                break
                
            # Heuristic 1: Fill checks
            if direction == 1:
                if p_trade < limit_price:  # Traded through!
                    filled = True
                    t_fill = t_trade
                    break
                elif p_trade == limit_price:
                    if resting_size == 0.0:  # Front of queue!
                        filled = True
                        t_fill = t_trade
                        break
                    cum_vol_at_limit += sz_trade
                    if cum_vol_at_limit >= resting_size:  # Queue cleared!
                        filled = True
                        t_fill = t_trade
                        break
            else:
                if p_trade > limit_price:  # Traded through!
                    filled = True
                    t_fill = t_trade
                    break
                elif p_trade == limit_price:
                    if resting_size == 0.0:  # Front of queue!
                        filled = True
                        t_fill = t_trade
                        break
                    cum_vol_at_limit += sz_trade
                    if cum_vol_at_limit >= resting_size:  # Queue cleared!
                        filled = True
                        t_fill = t_trade
                        break
                        
        if not filled:
            # Order canceled or pulled
            continue
            
        # Find bar index of fill time
        fill_bar_idx_pos = np.searchsorted(start_times, t_fill, side='right') - 1
        if fill_bar_idx_pos >= 0 and t_fill <= end_times[fill_bar_idx_pos]:
            entry_idx = fill_bar_idx_pos
        else:
            entry_idx = idx
            
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
            if exit_type == "pt":
                cost = maker_fee + maker_fee
            else:
                cost = maker_fee + taker_fee + slippage
                
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

def run_market_backtest_v8(symbol):
    asym_params = ASYMM_PARAMS[symbol]
    mid = asym_params["market_id"]
    
    data_dir = "data"
    trade_files = sorted(glob.glob(os.path.join(data_dir, f"raw_lighter_trades_{mid}_*.jsonl.zst")))
    book_files = sorted(glob.glob(os.path.join(data_dir, f"raw_lighter_book_{mid}_*.jsonl.zst")))
    
    if not trade_files or not book_files:
        print(f"\nNo data files found for market {symbol}. Skipping...")
        return None
        
    print(f"\n=======================================================")
    print(f" PROCESSING MARKET (V8 AGGRESSIVE QUEUE): {symbol} (Market ID: {mid})")
    print(f"=======================================================")
    
    # Ingest Trades
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
    bars_df = build_volume_bars_from_events(trades, v_thresh)
    
    df_features, book_times, best_bids, best_asks, best_bid_szs, best_ask_szs = compute_bar_features_streaming_v8(
        bars_df, book_files, trades, z_window=100
    )
    
    print("Applying Asymmetric Triple Barrier Method exits (V8 Aggressive Queue + Z-Score Pull)...")
    # Standard: 300ms latency, 0% fees, 0.5 bps slippage (only on taker exits)
    std_events = apply_lighter_triple_barriers_v8(
        symbol, df_features, book_times, best_bids, best_asks, best_bid_szs, best_ask_szs, trades,
        asymm_params=asym_params, latency_ms=300, maker_latency_ms=200,
        maker_fee=0.0, taker_fee=0.0, slippage=0.00005
    )
    
    # Premium: 140ms latency, 0.4 bps maker fee, 2.8 bps taker fee, 0.2 bps slippage (on taker exits)
    prem_events = apply_lighter_triple_barriers_v8(
        symbol, df_features, book_times, best_bids, best_asks, best_bid_szs, best_ask_szs, trades,
        asymm_params=asym_params, latency_ms=140, maker_latency_ms=0,
        maker_fee=0.00004, taker_fee=0.00028, slippage=0.00002
    )
    
    print(f"Standard Tier: Generated {len(std_events)} events.")
    print(f"Premium Tier: Generated {len(prem_events)} events.")
    
    n_bars = len(df_features)
    train_end = int(n_bars * 0.6)
    val_start = train_end + 1
    
    std_model = None
    if not std_events.empty:
        std_train_purged = purge_and_embargo_lighter(df_features, std_events, 0, train_end, val_start, 0.05)
        if len(std_train_purged) > 0:
            std_model = train_lighter_meta_labeler_v6(df_features, std_train_purged)
            if std_model is not None:
                import joblib
                os.makedirs("models", exist_ok=True)
                joblib.dump(std_model, f"models/std_model_{symbol}.joblib")
            
    prem_model = None
    if not prem_events.empty:
        prem_train_purged = purge_and_embargo_lighter(df_features, prem_events, 0, train_end, val_start, 0.05)
        if len(prem_train_purged) > 0:
            prem_model = train_lighter_meta_labeler_v6(df_features, prem_train_purged)
            if prem_model is not None:
                import joblib
                os.makedirs("models", exist_ok=True)
                joblib.dump(prem_model, f"models/prem_model_{symbol}.joblib")
            
    std_val_events = std_events[std_events["entry_idx"] >= val_start].copy() if not std_events.empty else pd.DataFrame()
    prem_val_events = prem_events[prem_events["entry_idx"] >= val_start].copy() if not prem_events.empty else pd.DataFrame()
    
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
    print(f"            LIGHTER PERFORMANCE (V8 QUEUE MODEL) ({symbol})")
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
        res = run_market_backtest_v8(sym)
        if res:
            results[sym] = res
            
    if results:
        md_report = """# Aggressive Front-Running & Normalized Pull Backtesting Report (V8)

This report presents backtesting results with passive maker limit orders, aggressive front-running queue positioning (one tick improvement when spread > 1 tick), and rolling Z-score velocity-based cancel/pull filters.

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
            
        report_path = "/kaggle/research7/multi_pair_61h_report_v8.md"
        with open(report_path, "w") as f:
            f.write(md_report)
        print(f"\nWritten V8 Queue Maker summary report to: {report_path}")

        with open("/kaggle/research7/data/v8_maker_scorecard.json", "w") as f:
            json.dump(results, f, indent=4)

if __name__ == "__main__":
    main()
