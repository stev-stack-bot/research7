import os
import sys
import glob
import io
import json
import numpy as np
import pandas as pd
from bisect import bisect_left
import zstandard as zstd
from sklearn.ensemble import RandomForestClassifier

# Add src to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.lighter_meta_labeler import purge_and_embargo_lighter
from src.lighter_features import compute_ofi_delta

MARKET_PARAMS = {
    "ETH": {"market_id": "0", "z_threshold": 0.5, "pt_mult": 1.0, "sl_mult": 1.0, "hold_bars": 10, "v_thresh": 78.4},
    "BTC": {"market_id": "1", "z_threshold": 0.5, "pt_mult": 5.0, "sl_mult": 2.0, "hold_bars": 10, "v_thresh": 3.43},
    "SOL": {"market_id": "2", "z_threshold": 0.5, "pt_mult": 2.0, "sl_mult": 2.0, "hold_bars": 5, "v_thresh": 513.8}
}

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

def stream_jsonl_zst(file_paths):
    dctx = zstd.ZstdDecompressor()
    for file_path in file_paths:
        with open(file_path, 'rb') as fh:
            with dctx.stream_reader(fh) as reader:
                text_stream = io.TextIOWrapper(reader, encoding='utf-8')
                for line in text_stream:
                    yield json.loads(line)

def build_volume_bars_from_events(trades, v_thresh):
    bars = []
    cum_vol = 0.0
    bar_start_idx = 0
    bar_index = 0
    
    for idx, row in enumerate(trades):
        cum_vol += row["size"]
        if cum_vol >= v_thresh:
            bar_trades = trades[bar_start_idx : idx + 1]
            prices = [t["price"] for t in bar_trades]
            sizes = [t["size"] for t in bar_trades]
            times = [t["transaction_time"] for t in bar_trades]
            
            bar_start_time = int(min(times))
            bar_end_time = int(row["transaction_time"])
            
            bars.append({
                "bar_index": bar_index,
                "start_time": bar_start_time,
                "end_time": bar_end_time,
                "open": float(prices[0]),
                "high": float(max(prices)),
                "low": float(min(prices)),
                "close": float(row["price"]),
                "volume": float(sum(sizes)),
                "trade_count": len(prices)
            })
            
            cum_vol = 0.0
            bar_start_idx = idx + 1
            bar_index += 1
            
    # Include remaining partial bar if any
    if bar_start_idx < len(trades):
        bar_trades = trades[bar_start_idx:]
        prices = [t["price"] for t in bar_trades]
        sizes = [t["size"] for t in bar_trades]
        times = [t["transaction_time"] for t in bar_trades]
        
        bars.append({
            "bar_index": bar_index,
            "start_time": int(min(times)),
            "end_time": int(max(times)),
            "open": float(prices[0]),
            "high": float(max(prices)),
            "low": float(min(prices)),
            "close": float(prices[-1]),
            "volume": float(sum(sizes)),
            "trade_count": len(prices)
        })
        
    return pd.DataFrame(bars)

def train_lighter_meta_labeler_v3(df, train_events):
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
    
    model = RandomForestClassifier(n_estimators=100, max_depth=4, random_state=42)
    model.fit(X_train, y_train)
    
    return model

def simulate_lighter_backtest_v3(df, events_df, maker_fee=0.0, taker_fee=0.0, slippage=0.0, meta_model=None, prob_thresh=0.5):
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
            # Entry is taker order. Exit is maker (if pt) or taker (if sl or time).
            if exit_type == "pt":
                cost = taker_fee + maker_fee + slippage
            else:
                cost = taker_fee + taker_fee + slippage * 2
                
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
    
    # Calculate performance metrics
    win_rate = (t_df["net_return"] > 0).mean()
    gross_gains = t_df[t_df["net_return"] > 0]["net_return"].sum()
    gross_losses = abs(t_df[t_df["net_return"] < 0]["net_return"].sum())
    profit_factor = gross_gains / gross_losses if gross_losses > 0 else float("inf")
    
    mean_ret = t_df["net_return"].mean()
    std_ret = t_df["net_return"].std()
    # Sharpe daily approximation
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

def compute_bar_features_streaming(bars_df, book_files, trades, z_window=100):
    bar_starts = bars_df["start_time"].values
    bar_ends = bars_df["end_time"].values
    max_bar_idx = len(bars_df) - 1
    max_bar_end = bar_ends[-1]
    
    # Initialize run accumulators
    n_bars = len(bars_df)
    bar_cofi = np.zeros(n_bars)
    bar_cofi_l1 = np.zeros(n_bars)
    bar_spread_sum = np.zeros(n_bars)
    bar_spread_count = np.zeros(n_bars)
    bar_last_levels = [None] * n_bars
    bar_prev_levels = [None] * n_bars
    
    # Global compact order book lists
    book_times_list = []
    best_bids_list = []
    best_asks_list = []
    
    # Order book state
    current_bids = {}
    current_asks = {}
    
    print("Streaming book updates to calculate features on-the-fly...")
    
    update_count = 0
    for msg in stream_jsonl_zst(book_files):
        ob_data = msg.get("order_book", {})
        if not ob_data:
            continue
        
        # If snapshot is received, clear local state
        if len(ob_data.get("bids", [])) > 100 or len(ob_data.get("asks", [])) > 100:
            current_bids.clear()
            current_asks.clear()

        # update bids
        for b in ob_data.get("bids", []):
            price = float(b["price"])
            size = float(b["size"])
            if size == 0.0:
                current_bids.pop(price, None)
            else:
                current_bids[price] = size
                
        # update asks
        for a in ob_data.get("asks", []):
            price = float(a["price"])
            size = float(a["size"])
            if size == 0.0:
                current_asks.pop(price, None)
            else:
                current_asks[price] = size
        
        if not current_bids or not current_asks:
            continue
            
        # Prune old levels to keep dictionaries small (do it every 500 updates instead of every update)
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
        
        # Sort and slice (highly optimized: sort only the keys, then construct the top 5 dicts)
        sorted_bid_keys = sorted(current_bids.keys(), reverse=True)[:5]
        sorted_bids = [{"px": p, "sz": current_bids[p]} for p in sorted_bid_keys]
        
        sorted_ask_keys = sorted(current_asks.keys())[:5]
        sorted_asks = [{"px": p, "sz": current_asks[p]} for p in sorted_ask_keys]
        
        ts_us = int(ob_data.get("last_updated_at") or msg.get("last_updated_at"))
        
        # Append to compact lists (only best bid/ask)
        book_times_list.append(ts_us)
        best_bids_list.append(sorted_bids[0]["px"])
        best_asks_list.append(sorted_asks[0]["px"])
        
        # Determine bar index
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
    
    # Convert compact lists to NumPy arrays
    book_times = np.array(book_times_list, dtype=np.int64)
    best_bids = np.array(best_bids_list, dtype=np.float64)
    best_asks = np.array(best_asks_list, dtype=np.float64)
    
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
    
    # Calculate rolling z-scores
    rolling_mean = bars_df["cofi"].rolling(window=z_window, min_periods=1).mean()
    rolling_std = bars_df["cofi"].rolling(window=z_window, min_periods=1).std().fillna(1.0)
    bars_df["cofi_z"] = (bars_df["cofi"] - rolling_mean) / rolling_std
    
    rolling_mean_l1 = bars_df["cofi_l1"].rolling(window=z_window, min_periods=1).mean()
    rolling_std_l1 = bars_df["cofi_l1"].rolling(window=z_window, min_periods=1).std().fillna(1.0)
    bars_df["cofi_l1_z"] = (bars_df["cofi_l1"] - rolling_mean_l1) / rolling_std_l1
    
    # Returns and micro-returns
    bars_df["ret"] = np.log(bars_df["close"] / bars_df["close"].shift(1)).fillna(0.0)
    bars_df["micro_ret"] = np.log(bars_df["micro_price"] / bars_df["micro_price"].shift(1)).fillna(0.0)
    
    # Volatility
    bars_df["volatility"] = bars_df["ret"].rolling(window=z_window, min_periods=1).std().fillna(0.0001)
    bars_df["volatility_ratio"] = (
        bars_df["ret"].rolling(window=10, min_periods=1).std() / 
        bars_df["volatility"]
    ).fillna(1.0)
    
    # Bar duration
    bars_df["duration"] = (bars_df["end_time"] - bars_df["start_time"]) / 1000000.0
    
    # Momentum (Lagged Returns)
    bars_df["ret_lag1"] = bars_df["ret"].shift(1).fillna(0.0)
    bars_df["ret_lag2"] = bars_df["ret"].shift(2).fillna(0.0)
    
    # Group trades by bar index
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
            
        # VPIN and Signed Volume
        buy_vol = 0.0
        sell_vol = 0.0
        total_vol = 0.0
        
        for trade in bar_trades:
            p_trade = trade["price"]
            sz_trade = trade["size"]
            t_trade = trade["transaction_time"]
            
            # Find closest book state in book_times
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
        
        # Gini of Trade Sizes
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
            
        # Tick-Path Efficiency
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
    
    # Velocity
    bars_df["velocity"] = bars_df.apply(
        lambda r: r["volume"] / r["duration"] if r["duration"] > 0 else 0.0, axis=1
    )
    
    # --- 6 NEW MICROSTRUCTURAL FEATURES ---
    
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
    
    # Target
    bars_df["next_ret"] = bars_df["ret"].shift(-1)
    
    return bars_df, book_times, best_bids, best_asks

def apply_lighter_triple_barriers_opt(df, book_times, best_bids, best_asks, trade_events, pt_mult=3.0, sl_mult=1.0, hold_bars=10, z_threshold=1.5, latency_ms=300, maker_latency_ms=200, use_composite_filter=False):
    events = []
    trade_times = np.array([t["transaction_time"] for t in trade_events], dtype=np.int64)
    trade_prices = np.array([t["price"] for t in trade_events], dtype=np.float64)
    
    for idx, row in df.iterrows():
        cofi_z = row["cofi_z"]
        if cofi_z >= z_threshold:
            direction = 1  # Long
        elif cofi_z <= -z_threshold:
            direction = -1  # Short
        else:
            continue
            
        if use_composite_filter:
            # 1. Spread must not be abnormally wide (spread_z < 1.5)
            if row["spread_z"] > 1.5:
                continue
            # 2. Flow toxicity must not be extremely high (vpin < 0.8)
            if row["vpin"] > 0.8:
                continue
            # 3. Market should be in a trending state (Hurst exponent > 0.45 or autocorr_ret > 0.0)
            if row["hurst"] < 0.45 and row["autocorr_ret"] <= 0.0:
                continue
            # 4. Market should not be completely inactive (volume clock acceleration > 0.2)
            if row["volume_accel"] < 0.2:
                continue
                
        signal_time = row["end_time"]
        vol = row["volatility"]
        
        # entry taker execution time
        t_entry_exec = signal_time + latency_ms * 1000
        
        book_idx = np.searchsorted(book_times, t_entry_exec)
        if book_idx >= len(book_times):
            continue
            
        entry_price = best_asks[book_idx] if direction == 1 else best_bids[book_idx]
        
        # entry bar index
        entry_bar_series = df[(df["start_time"] <= t_entry_exec) & (t_entry_exec <= df["end_time"])]
        if entry_bar_series.empty:
            if t_entry_exec > df["end_time"].max():
                continue
            entry_idx = idx
        else:
            entry_idx = int(entry_bar_series.iloc[0]["bar_index"])
            
        # barriers
        pt_barrier = entry_price * (1 + pt_mult * vol * direction)
        sl_barrier = entry_price * (1 - sl_mult * vol * direction)
        
        t_maker_active = t_entry_exec + maker_latency_ms * 1000
        
        expiry_bar_idx = min(entry_idx + hold_bars, len(df) - 1)
        t_expiry = df.loc[expiry_bar_idx, "end_time"]
        
        # Search subsequent trades
        first_trade_idx = np.searchsorted(trade_times, t_entry_exec)
        
        exit_time = t_expiry
        exit_type = "time"
        
        for k in range(first_trade_idx, len(trade_events)):
            t_trade = trade_times[k]
            if t_trade > t_expiry:
                break
                
            p_trade = trade_prices[k]
            
            # Check Stop Loss first (conservative)
            if direction == 1 and p_trade <= sl_barrier:
                exit_time = t_trade
                exit_type = "sl"
                break
            elif direction == -1 and p_trade >= sl_barrier:
                exit_time = t_trade
                exit_type = "sl"
                break
                
            # Check Profit Target
            if t_trade >= t_maker_active:
                if direction == 1 and p_trade >= pt_barrier:
                    exit_time = t_trade
                    exit_type = "pt"
                    break
                elif direction == -1 and p_trade <= pt_barrier:
                    exit_time = t_trade
                    exit_type = "pt"
                    break
                    
        # Exit fill price lookup
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
                
        # Exit bar index lookup
        exit_bar_series = df[(df["start_time"] <= exit_time) & (exit_time <= df["end_time"])]
        if exit_bar_series.empty:
            if exit_time > df["end_time"].max():
                exit_idx = len(df) - 1
            else:
                exit_idx = entry_idx
        else:
            exit_idx = int(exit_bar_series.iloc[0]["bar_index"])
            
        raw_ret = (exit_price - entry_price) / entry_price * direction
        
        events.append({
            "entry_idx": entry_idx,
            "signal_idx": idx,
            "entry_time": t_entry_exec,
            "direction": direction,
            "exit_idx": exit_idx,
            "exit_time": exit_time,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "exit_type": exit_type,
            "raw_return": raw_ret,
            "label": 1 if exit_type == "pt" else 0
        })
        
    return pd.DataFrame(events)

def run_market_backtest(symbol):
    params = MARKET_PARAMS[symbol]
    mid = params["market_id"]
    
    data_dir = "data"
    trade_files = sorted(glob.glob(os.path.join(data_dir, f"raw_lighter_trades_{mid}_*.jsonl.zst")))
    book_files = sorted(glob.glob(os.path.join(data_dir, f"raw_lighter_book_{mid}_*.jsonl.zst")))
    
    if not trade_files or not book_files:
        print(f"\nNo data files found for market {symbol} (Market ID: {mid}). Skipping...")
        return None
        
    print(f"\n=======================================================")
    print(f" PROCESSING MARKET: {symbol} (Market ID: {mid})")
    print(f"=======================================================")
    print(f"Found {len(trade_files)} trade files and {len(book_files)} book files.")
    
    # 1. Ingest Trades
    print("Ingesting trades...")
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
    
    print(f"Total trades ingested: {len(trades)}")
    total_vol = sum(t["size"] for t in trades)
    print(f"Total trade volume: {total_vol:.5f} {symbol}")
    
    v_thresh = params["v_thresh"]
    print(f"Using fixed volume threshold per bar: {v_thresh} {symbol}")
    
    # 2. Build volume bars
    print("Building volume bars...")
    bars_df = build_volume_bars_from_events(trades, v_thresh)
    print(f"Constructed {len(bars_df)} volume bars.")
    
    # 3 & 4. Map books and compute features streaming (including 6 new features)
    df_features, book_times, best_bids, best_asks = compute_bar_features_streaming(
        bars_df, book_files, trades, z_window=100
    )
    
    print("Features computed successfully.")
    
    # 5. Apply Triple Barrier Exits (Generates Base vs. Composite-Filtered Events)
    print("Applying Triple Barrier Method exits...")
    # Standard: 300ms taker latency, 200ms maker latency
    std_base_events = apply_lighter_triple_barriers_opt(
        df_features, book_times, best_bids, best_asks, trades,
        pt_mult=params["pt_mult"], sl_mult=params["sl_mult"], hold_bars=params["hold_bars"],
        z_threshold=params["z_threshold"], latency_ms=300, maker_latency_ms=200,
        use_composite_filter=False
    )
    std_filt_events = apply_lighter_triple_barriers_opt(
        df_features, book_times, best_bids, best_asks, trades,
        pt_mult=params["pt_mult"], sl_mult=params["sl_mult"], hold_bars=params["hold_bars"],
        z_threshold=params["z_threshold"], latency_ms=300, maker_latency_ms=200,
        use_composite_filter=True
    )
    
    # Premium: 140ms taker latency, 0ms maker latency
    prem_base_events = apply_lighter_triple_barriers_opt(
        df_features, book_times, best_bids, best_asks, trades,
        pt_mult=params["pt_mult"], sl_mult=params["sl_mult"], hold_bars=params["hold_bars"],
        z_threshold=params["z_threshold"], latency_ms=140, maker_latency_ms=0,
        use_composite_filter=False
    )
    prem_filt_events = apply_lighter_triple_barriers_opt(
        df_features, book_times, best_bids, best_asks, trades,
        pt_mult=params["pt_mult"], sl_mult=params["sl_mult"], hold_bars=params["hold_bars"],
        z_threshold=params["z_threshold"], latency_ms=140, maker_latency_ms=0,
        use_composite_filter=True
    )
    
    print(f"Standard Tier: Base events = {len(std_base_events)}, Filtered events = {len(std_filt_events)}")
    print(f"Premium Tier: Base events = {len(prem_base_events)}, Filtered events = {len(prem_filt_events)}")
    
    # 6. Splitting Data and training models
    n_bars = len(df_features)
    train_end = int(n_bars * 0.6)
    val_start = train_end + 1
    
    print(f"Splitting data: Train index 0-{train_end}, Validation index >= {val_start}")
    
    # Train separate meta-labeler models for base vs filtered setups
    std_base_model = None
    if not std_base_events.empty:
        std_base_train_purged = purge_and_embargo_lighter(df_features, std_base_events, 0, train_end, val_start, 0.05)
        if len(std_base_train_purged) > 0:
            std_base_model = train_lighter_meta_labeler_v3(df_features, std_base_train_purged)
            
    std_filt_model = None
    if not std_filt_events.empty:
        std_filt_train_purged = purge_and_embargo_lighter(df_features, std_filt_events, 0, train_end, val_start, 0.05)
        if len(std_filt_train_purged) > 0:
            std_filt_model = train_lighter_meta_labeler_v3(df_features, std_filt_train_purged)
            
    prem_base_model = None
    if not prem_base_events.empty:
        prem_base_train_purged = purge_and_embargo_lighter(df_features, prem_base_events, 0, train_end, val_start, 0.05)
        if len(prem_base_train_purged) > 0:
            prem_base_model = train_lighter_meta_labeler_v3(df_features, prem_base_train_purged)
            
    prem_filt_model = None
    if not prem_filt_events.empty:
        prem_filt_train_purged = purge_and_embargo_lighter(df_features, prem_filt_events, 0, train_end, val_start, 0.05)
        if len(prem_filt_train_purged) > 0:
            prem_filt_model = train_lighter_meta_labeler_v3(df_features, prem_filt_train_purged)
            
    # Filter validation events
    std_val_base = std_base_events[std_base_events["entry_idx"] >= val_start].copy() if not std_base_events.empty else pd.DataFrame()
    std_val_filt = std_filt_events[std_filt_events["entry_idx"] >= val_start].copy() if not std_filt_events.empty else pd.DataFrame()
    
    prem_val_base = prem_base_events[prem_base_events["entry_idx"] >= val_start].copy() if not prem_base_events.empty else pd.DataFrame()
    prem_val_filt = prem_filt_events[prem_filt_events["entry_idx"] >= val_start].copy() if not prem_filt_events.empty else pd.DataFrame()
    
    # 7. Run Backtests
    # Standard costs: 0% maker/taker, 0.5 bps slippage
    std_baseline_res = simulate_lighter_backtest_v3(df_features, std_val_base, maker_fee=0.0, taker_fee=0.0, slippage=0.00005)
    std_filt_res     = simulate_lighter_backtest_v3(df_features, std_val_filt, maker_fee=0.0, taker_fee=0.0, slippage=0.00005)
    std_meta_res     = simulate_lighter_backtest_v3(df_features, std_val_base, maker_fee=0.0, taker_fee=0.0, slippage=0.00005, meta_model=std_base_model, prob_thresh=0.5)
    std_comb_res     = simulate_lighter_backtest_v3(df_features, std_val_filt, maker_fee=0.0, taker_fee=0.0, slippage=0.00005, meta_model=std_filt_model, prob_thresh=0.5)
    
    # Premium costs: 0.4 bps maker, 2.8 bps taker, 0.2 bps slippage
    prem_baseline_res = simulate_lighter_backtest_v3(df_features, prem_val_base, maker_fee=0.00004, taker_fee=0.00028, slippage=0.00002)
    prem_filt_res     = simulate_lighter_backtest_v3(df_features, prem_val_filt, maker_fee=0.00004, taker_fee=0.00028, slippage=0.00002)
    prem_meta_res     = simulate_lighter_backtest_v3(df_features, prem_val_base, maker_fee=0.00004, taker_fee=0.00028, slippage=0.00002, meta_model=prem_base_model, prob_thresh=0.5)
    prem_comb_res     = simulate_lighter_backtest_v3(df_features, prem_val_filt, maker_fee=0.00004, taker_fee=0.00028, slippage=0.00002, meta_model=prem_filt_model, prob_thresh=0.5)
    
    test_bars = df_features[df_features["bar_index"] >= val_start]
    if not test_bars.empty and len(test_bars) > 1:
        bench_ret = (test_bars.iloc[-1]["close"] - test_bars.iloc[0]["close"]) / test_bars.iloc[0]["close"]
    else:
        bench_ret = 0.0
        
    print("\n=======================================================")
    print(f"            LIGHTER PERFORMANCE REPORT ({symbol})")
    print("=======================================================")
    print(f"Benchmark Buy-and-Hold Return: {bench_ret * 100:.4f}%")
    print("-------------------------------------------------------")
    print("STANDARD TIER (0% fees, 300ms taker / 200ms maker latency):")
    print(f"  - Baseline (No Filt, No ML) Return: {std_baseline_res['metrics']['total_return']*100:+.4f}% | PF: {std_baseline_res['metrics']['profit_factor']:.2f} | Trades: {std_baseline_res['metrics']['trade_count']}")
    print(f"  - Filtered (Filt, No ML)    Return: {std_filt_res['metrics']['total_return']*100:+.4f}% | PF: {std_filt_res['metrics']['profit_factor']:.2f} | Trades: {std_filt_res['metrics']['trade_count']}")
    print(f"  - Meta-Labeled (No Filt, ML) Return: {std_meta_res['metrics']['total_return']*100:+.4f}% | PF: {std_meta_res['metrics']['profit_factor']:.2f} | Trades: {std_meta_res['metrics']['trade_count']}")
    print(f"  - Combined Strategy (Filt, ML) Return: {std_comb_res['metrics']['total_return']*100:+.4f}% | PF: {std_comb_res['metrics']['profit_factor']:.2f} | Trades: {std_comb_res['metrics']['trade_count']}")
    print("-------------------------------------------------------")
    print("PREMIUM TIER (2.8 bps taker / 0.4 bps maker, 140ms taker latency):")
    print(f"  - Baseline (No Filt, No ML) Return: {prem_baseline_res['metrics']['total_return']*100:+.4f}% | PF: {prem_baseline_res['metrics']['profit_factor']:.2f} | Trades: {prem_baseline_res['metrics']['trade_count']}")
    print(f"  - Filtered (Filt, No ML)    Return: {prem_filt_res['metrics']['total_return']*100:+.4f}% | PF: {prem_filt_res['metrics']['profit_factor']:.2f} | Trades: {prem_filt_res['metrics']['trade_count']}")
    print(f"  - Meta-Labeled (No Filt, ML) Return: {prem_meta_res['metrics']['total_return']*100:+.4f}% | PF: {prem_meta_res['metrics']['profit_factor']:.2f} | Trades: {prem_meta_res['metrics']['trade_count']}")
    print(f"  - Combined Strategy (Filt, ML) Return: {prem_comb_res['metrics']['total_return']*100:+.4f}% | PF: {prem_comb_res['metrics']['profit_factor']:.2f} | Trades: {prem_comb_res['metrics']['trade_count']}")
    print("=======================================================")
    
    # 8. Leakage Check
    print("\n--- Leakage and Integrity Checks ---")
    leak_detected = False
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
        
    return {
        "symbol": symbol,
        "bench_ret": bench_ret,
        "std_baseline": std_baseline_res,
        "std_filtered": std_filt_res,
        "std_meta": std_meta_res,
        "std_combined": std_comb_res,
        "prem_baseline": prem_baseline_res,
        "prem_filtered": prem_filt_res,
        "prem_meta": prem_meta_res,
        "prem_combined": prem_comb_res
    }

def main():
    market_arg = sys.argv[1].upper() if len(sys.argv) > 1 else "ALL"
    
    if market_arg == "ALL":
        symbols = ["ETH", "BTC", "SOL"]
    elif market_arg in MARKET_PARAMS:
        symbols = [market_arg]
    else:
        print(f"Invalid market argument: {market_arg}. Must be one of: ALL, ETH, BTC, SOL")
        return
        
    results = {}
    for sym in symbols:
        res = run_market_backtest(sym)
        if res:
            results[sym] = res
            
    # Save a summary report to markdown if we generated any results
    if results:
        md_report = """# Advanced Multi-Pair Backtesting Report (14-Hour Dataset)

This report presents the backtesting results of the OBI Scalper strategy with 6 new microstructural features and a 2x2 comparison of signal filtering and machine learning.

## Standard Tier Performance Summary Table (0% fees, 300ms taker / 200ms maker latency)

| Pair | Benchmark Return | Baseline Return (No Filt, No ML) | Baseline PF | Filtered Return (Filt, No ML) | Filtered PF | Meta-Labeled (No Filt, ML) | Meta-Labeled PF | Combined Return (Filt, ML) | Combined PF |
|------|------------------|----------------------------------|-------------|------------------------------|-------------|----------------------------|-----------------|----------------------------|-------------|
"""
        for sym, r in results.items():
            b_ret = r["bench_ret"] * 100
            
            std_base_ret = r["std_baseline"]["metrics"]["total_return"] * 100
            std_base_pf  = r["std_baseline"]["metrics"]["profit_factor"]
            
            std_filt_ret = r["std_filtered"]["metrics"]["total_return"] * 100
            std_filt_pf  = r["std_filtered"]["metrics"]["profit_factor"]
            
            std_meta_ret = r["std_meta"]["metrics"]["total_return"] * 100
            std_meta_pf  = r["std_meta"]["metrics"]["profit_factor"]
            
            std_comb_ret = r["std_combined"]["metrics"]["total_return"] * 100
            std_comb_pf  = r["std_combined"]["metrics"]["profit_factor"]
            
            md_report += f"| {sym} | {b_ret:.4f}% | {std_base_ret:+.4f}% | {std_base_pf:.2f} | {std_filt_ret:+.4f}% | {std_filt_pf:.2f} | {std_meta_ret:+.4f}% | {std_meta_pf:.2f} | {std_comb_ret:+.4f}% | {std_comb_pf:.2f} |\n"

        md_report += """
## Premium Tier Performance Summary Table (2.8 bps taker / 0.4 bps maker, 140ms taker latency)

| Pair | Benchmark Return | Baseline Return (No Filt, No ML) | Baseline PF | Filtered Return (Filt, No ML) | Filtered PF | Meta-Labeled (No Filt, ML) | Meta-Labeled PF | Combined Return (Filt, ML) | Combined PF |
|------|------------------|----------------------------------|-------------|------------------------------|-------------|----------------------------|-----------------|----------------------------|-------------|
"""
        for sym, r in results.items():
            b_ret = r["bench_ret"] * 100
            
            prem_base_ret = r["prem_baseline"]["metrics"]["total_return"] * 100
            prem_base_pf  = r["prem_baseline"]["metrics"]["profit_factor"]
            
            prem_filt_ret = r["prem_filtered"]["metrics"]["total_return"] * 100
            prem_filt_pf  = r["prem_filtered"]["metrics"]["profit_factor"]
            
            prem_meta_ret = r["prem_meta"]["metrics"]["total_return"] * 100
            prem_meta_pf  = r["prem_meta"]["metrics"]["profit_factor"]
            
            prem_comb_ret = r["prem_combined"]["metrics"]["total_return"] * 100
            prem_comb_pf  = r["prem_combined"]["metrics"]["profit_factor"]
            
            md_report += f"| {sym} | {b_ret:.4f}% | {prem_base_ret:+.4f}% | {prem_base_pf:.2f} | {prem_filt_ret:+.4f}% | {prem_filt_pf:.2f} | {prem_meta_ret:+.4f}% | {prem_meta_pf:.2f} | {prem_comb_ret:+.4f}% | {prem_comb_pf:.2f} |\n"
            
        report_path = "/kaggle/research7/multi_pair_14h_report_v3.md"
        with open(report_path, "w") as f:
            f.write(md_report)
        print(f"\nWritten summary report to: {report_path}")

if __name__ == "__main__":
    main()
