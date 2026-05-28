import asyncio
import json
import os
import sys
import time
import numpy as np
import pandas as pd
from bisect import bisect_left
import joblib

# Add src to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.lighter_features import compute_ofi_delta, compute_lighter_bar_features

# V8 globals matching run_lighter_pipeline_v8_maker.py
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

def compute_lighter_bar_features_v8(bars_df, book_bar_mapping, trade_events, levels_count=5, z_window=100):
    """
    Compute V8 specific features by adding advanced metrics on top of standard OFI/spread/volatility features.
    """
    # 1. Compute standard features
    df = compute_lighter_bar_features(bars_df, book_bar_mapping, trade_events, levels_count, z_window)
    
    # 2. Extract books mapped to bar indexes to calculate signed volume
    bar_to_books = {}
    for bar_idx, book_row in book_bar_mapping:
        if bar_idx not in bar_to_books:
            bar_to_books[bar_idx] = []
        bar_to_books[bar_idx].append(book_row)
        
    all_books = sorted([row for _, row in book_bar_mapping], key=lambda x: x["time"])
    book_times = [b["time"] for b in all_books]
    
    signed_vol_values = []
    for idx, row in df.iterrows():
        t_start = row["start_time"]
        t_end = row["end_time"]
        bar_trades = [t for t in trade_events if t_start <= t["transaction_time"] <= t_end]
        if not bar_trades:
            signed_vol_values.append(0.0)
            continue
            
        buy_vol = 0.0
        sell_vol = 0.0
        for trade in bar_trades:
            p_trade = trade["price"]
            sz_trade = trade["size"]
            t_trade = trade["transaction_time"]
            
            if book_times:
                book_idx = bisect_left(book_times, t_trade)
                if book_idx >= len(all_books):
                    book_idx = len(all_books) - 1
                closest_book = all_books[book_idx]
                try:
                    bid_px = float(closest_book["levels"][0][0]["px"])
                    ask_px = float(closest_book["levels"][1][0]["px"])
                    mid_px = (bid_px + ask_px) / 2.0
                except Exception:
                    mid_px = p_trade
            else:
                mid_px = p_trade
                
            if p_trade >= mid_px:
                buy_vol += sz_trade
            else:
                sell_vol += sz_trade
        signed_vol_values.append(buy_vol - sell_vol)
        
    df["signed_volume"] = signed_vol_values
    
    # 3. Compute advanced features
    df["price_diff"] = df["close"].diff().fillna(0.0)
    roll_cov = df["price_diff"].rolling(window=20, min_periods=5).cov(df["signed_volume"])
    roll_var = df["signed_volume"].rolling(window=20, min_periods=5).var().fillna(1.0)
    df["kyle_lambda"] = (roll_cov / roll_var).fillna(0.0)
    
    df["autocorr_ret"] = df["ret"].rolling(window=20, min_periods=5).apply(
        lambda x: x.autocorr(lag=1) if len(x) >= 5 else 0.0, raw=False
    ).fillna(0.0)
    
    df["amihud"] = (df["ret"].abs() / (df["volume"] + 1e-8)).rolling(window=20, min_periods=1).mean().fillna(0.0)
    
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
    df["hurst"] = df["close"].rolling(window=20, min_periods=5).apply(hurst_chunk, raw=True).fillna(0.5)
    
    duration_ema = df["duration"].ewm(span=20, min_periods=1).mean()
    df["volume_accel"] = (duration_ema / (df["duration"] + 1e-6)).fillna(1.0)
    
    spread_mean = df["avg_spread"].rolling(window=100, min_periods=1).mean()
    spread_std = df["avg_spread"].rolling(window=100, min_periods=1).std().fillna(1.0)
    df["spread_z"] = ((df["avg_spread"] - spread_mean) / spread_std).fillna(0.0)
    
    df["velocity_mean"] = df["velocity"].rolling(window=100, min_periods=10).mean().fillna(df["velocity"])
    df["velocity_std"] = df["velocity"].rolling(window=100, min_periods=10).std().fillna(1.0)
    
    return df

class LiveLighterSimulator:
    def __init__(self, market_id="1", symbol="BTC", tier="premium"):
        self.market_id = str(market_id)
        self.symbol = symbol.upper()
        self.tier = tier.lower()
        
        self.uri = "wss://mainnet.zklighter.elliot.ai/stream?readonly=true"
        
        # Load parameters
        self.params = ASYMM_PARAMS[self.symbol]
        self.tick_size = TICK_SIZES[self.symbol]
        self.feature_cols = FEATURE_COLS
        self.v_thresh = self.params["v_thresh"]
        
        # Load meta-labeler model
        tier_short = "prem" if self.tier == "premium" else "std"
        model_path = f"models/{tier_short}_model_{self.symbol}.joblib"
        if os.path.exists(model_path):
            self.meta_model = joblib.load(model_path)
            print(f"Loaded Random Forest Meta-Labeler model from {model_path}")
        else:
            self.meta_model = None
            print(f"No Meta-Labeler model found at {model_path}. Running baseline logic only.")
            
        # Order book state
        self.bids = {}
        self.asks = {}
        self.book_history = []  # List of dicts: {'time': ts_us, 'bids': ..., 'asks': ...}
        
        # Trades state for volume bars
        self.recent_trades = []
        self.bars = []          # List of bar dicts
        self.bar_index = 0
        self.cum_vol = 0.0
        self.bar_start_idx = 0
        self.bar_start_time = None
        
        # Strategy execution state
        self.resting_orders = [] # List of resting limit orders waiting to be filled or canceled
        self.active_trades = [] # List of active filled trades
        self.completed_trades = []
        self.df_features = pd.DataFrame()
        self.book_bar_mapping = []
        
        print(f"=======================================================")
        print(f"   LIGHTER REAL-TIME STRATEGY SIMULATOR (V8 MAKER)")
        print(f"=======================================================")
        print(f"  Target Market: {self.symbol} (ID: {self.market_id})")
        print(f"  Tier         : {self.tier.upper()}")
        print(f"  Model Loaded : {self.meta_model is not None}")
        print(f"=======================================================")

    def update_order_book(self, ob_data, ts_us):
        # Clear local order book state if a full snapshot is received
        if len(ob_data.get("bids", [])) > 100 or len(ob_data.get("asks", [])) > 100:
            self.bids.clear()
            self.asks.clear()

        # Update bids
        for b in ob_data.get("bids", []):
            price = float(b["price"])
            size = float(b["size"])
            if size == 0.0:
                self.bids.pop(price, None)
            else:
                self.bids[price] = size
                
        # Update asks
        for a in ob_data.get("asks", []):
            price = float(a["price"])
            size = float(a["size"])
            if size == 0.0:
                self.asks.pop(price, None)
            else:
                self.asks[price] = size

        # Prune old levels to keep dictionaries small (prevents RAM leaks)
        if self.bids and self.asks:
            best_bid = max(self.bids.keys())
            best_ask = min(self.asks.keys())
            mid_px = (best_bid + best_ask) / 2.0
            
            for px in list(self.bids.keys()):
                if px < mid_px * 0.95:
                    self.bids.pop(px)
            for px in list(self.asks.keys()):
                if px > mid_px * 1.05:
                    self.asks.pop(px)
                
        sorted_bids = sorted([{"px": p, "sz": s} for p, s in self.bids.items()], key=lambda x: x["px"], reverse=True)[:5]
        sorted_asks = sorted([{"px": p, "sz": s} for p, s in self.asks.items()], key=lambda x: x["px"])[:5]
        
        state = {
            "time": ts_us,
            "levels": [sorted_bids, sorted_asks],
            "bids": sorted_bids,
            "asks": sorted_asks
        }

        self.book_history.append(state)
        if len(self.book_history) > 2000:
            self.book_history.pop(0)
            
        return state

    def handle_trade(self, t, ts_us):
        trade_item = {
            "price": float(t["price"]),
            "size": float(t["size"]),
            "transaction_time": int(t["transaction_time"])
        }
        self.recent_trades.append(trade_item)
        self.cum_vol += trade_item["size"]
        
        # Initialize bar start time if new
        if self.bar_start_time is None:
            self.bar_start_time = trade_item["transaction_time"]
            
        # Check if bar is complete
        if self.cum_vol >= self.v_thresh:
            bar_trades = self.recent_trades[self.bar_start_idx:]
            bar_trades_df = pd.DataFrame(bar_trades)
            
            bar_end_time = trade_item["transaction_time"]
            bar_close = trade_item["price"]
            
            new_bar = {
                "bar_index": self.bar_index,
                "start_time": self.bar_start_time,
                "end_time": bar_end_time,
                "open": float(bar_trades[0]["price"]),
                "high": float(bar_trades_df["price"].max()),
                "low": float(bar_trades_df["price"].min()),
                "close": bar_close,
                "volume": float(self.cum_vol),
                "trade_count": len(bar_trades)
            }
            
            self.bars.append(new_bar)
            if len(self.bars) > 150:  # Kept 150 bars to support rolling features of z_window=100
                self.bars.pop(0)
                
            print(f"\n[+] Volume Bar {self.bar_index} Formed | Close: {bar_close:.2f} | Vol: {self.cum_vol:.3f} | Trades: {len(bar_trades)}")
            
            # Map book updates to this bar
            for state in self.book_history:
                if self.bar_start_time <= state["time"] <= bar_end_time:
                    self.book_bar_mapping.append((self.bar_index, state))
                    
            # Prune book_bar_mapping to match the active bars in self.bars
            min_active_bar_idx = self.bars[0]["bar_index"]
            self.book_bar_mapping = [item for item in self.book_bar_mapping if item[0] >= min_active_bar_idx]
            
            # Compute features & check signals
            self.process_features_and_signals()
            
            # Reset for next bar
            self.cum_vol = 0.0
            self.bar_start_time = None
            self.bar_index += 1
            
            # Prune recent_trades to match active bars
            min_active_time = self.bars[0]["start_time"]
            self.recent_trades = [t for t in self.recent_trades if t["transaction_time"] >= min_active_time]
            self.bar_start_idx = len(self.recent_trades)

    def process_features_and_signals(self):
        # Warm up for at least 102 bars to ensure rolling window (z_window=100) is stable
        if len(self.bars) < 102:
            print(f"  [Warming Up] Bars: {len(self.bars)}/102...")
            return
            
        bars_df = pd.DataFrame(self.bars)
        
        # Calculate features using z_window = 100
        try:
            df_feats = compute_lighter_bar_features_v8(
                bars_df, self.book_bar_mapping, self.recent_trades, levels_count=5, z_window=100
            )
            self.df_features = df_feats
        except Exception as e:
            print(f"Error computing features: {e}")
            return
            
        latest_row = df_feats.iloc[-1]
        cofi_z = latest_row["cofi_z"]
        vpin = latest_row["vpin"]
        spread = latest_row["avg_spread"]
        close_px = latest_row["close"]
        
        # Calculate 50-bar EMA trend
        ema_trend = df_feats["close"].ewm(span=50, adjust=False).mean().iloc[-1]
        
        # Signal check using Asymmetric parameters
        lp = self.params["long"]
        sp = self.params["short"]
        
        # Check Long (aligned with trend)
        score_long = 0
        if close_px > ema_trend:
            if cofi_z >= lp["z_threshold"]:
                score_long += 1
            if latest_row["micro_ret"] > 0:
                score_long += 1
            if latest_row["kyle_lambda"] > 0:
                score_long += 1
            if latest_row["depth_ratio"] > 1.0:
                score_long += 1
            if latest_row["autocorr_ret"] > 0:
                score_long += 1
                
        # Check Short (aligned with trend)
        score_short = 0
        if close_px < ema_trend:
            if cofi_z <= -sp["z_threshold"]:
                score_short += 1
            if latest_row["micro_ret"] < 0:
                score_short += 1
            if latest_row["kyle_lambda"] < 0:
                score_short += 1
            if latest_row["depth_ratio"] < 1.0:
                score_short += 1
            if latest_row["autocorr_ret"] > 0:
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
            
        if direction != 0:
            # Meta-Labeler filter
            if self.meta_model is not None:
                features = np.array([[latest_row[col] for col in self.feature_cols]])
                prob_probs = self.meta_model.predict_proba(features)[0]
                prob = prob_probs[1] if len(prob_probs) > 1 else (1.0 if self.meta_model.classes_[0] == 1 else 0.0)
                
                if prob < 0.5:
                    print(f"    [Meta-Labeler Veto] Vetoed trade: prediction prob {prob:.4f} < 0.5")
                    direction = 0
                else:
                    print(f"    [Meta-Labeler Approved] Approved trade: prediction prob {prob:.4f} >= 0.5")
                    
        if direction != 0:
            self.trigger_simulated_trade(direction, latest_row, pt_mult, sl_mult, hold_bars)

    def trigger_simulated_trade(self, direction, bar_row, pt_mult, sl_mult, hold_bars):
        signal_time = bar_row["end_time"]
        vol = bar_row["volatility"]
        
        # Simulate execution latency (300ms in microseconds = 300,000 for standard, 140ms = 140,000 for premium)
        latency_us = 140000 if self.tier == "premium" else 300000
        t_exec = signal_time + latency_us
        
        # Schedule the limit order entry placement to execute after latency
        asyncio.create_task(self.place_resting_order_after_latency(direction, t_exec, vol, bar_row["bar_index"], pt_mult, sl_mult, hold_bars))

    async def place_resting_order_after_latency(self, direction, t_exec, vol, bar_idx, pt_mult, sl_mult, hold_bars):
        # Wait the latency period (0.14s for premium, 0.3s for standard)
        await asyncio.sleep(0.14 if self.tier == "premium" else 0.3)
        
        # Find order book price at t_exec
        book_times = [b["time"] for b in self.book_history]
        if not book_times:
            return
            
        idx = bisect_left(book_times, t_exec)
        if idx >= len(self.book_history):
            idx = len(self.book_history) - 1
            
        book = self.book_history[idx]
        
        if not book["bids"] or not book["asks"]:
            return
            
        best_bid = float(book["bids"][0]["px"])
        best_ask = float(book["asks"][0]["px"])
        best_bid_sz = float(book["bids"][0]["sz"])
        best_ask_sz = float(book["asks"][0]["sz"])
        spread = best_ask - best_bid
        
        # AGGRESSIVE QUEUE FRONT-RUNNING LOGIC
        if direction == 1:
            if spread > self.tick_size * 1.001:
                limit_price = best_bid + self.tick_size
                resting_size = 0.0
            else:
                limit_price = best_bid
                resting_size = best_bid_sz
        else:
            if spread > self.tick_size * 1.001:
                limit_price = best_ask - self.tick_size
                resting_size = 0.0
            else:
                limit_price = best_ask
                resting_size = best_ask_sz
                
        # Limit order expiry/cancel is 30 seconds after execution
        t_cancel = t_exec + 30 * 1000000
        
        new_order = {
            "direction": direction,
            "limit_price": limit_price,
            "resting_size": resting_size,
            "cum_vol_at_limit": 0.0,
            "t_entry_exec": t_exec,
            "t_cancel": t_cancel,
            "vol": vol,
            "bar_idx": bar_idx,
            "pt_mult": pt_mult,
            "sl_mult": sl_mult,
            "hold_bars": hold_bars,
            "status": "RESTING"
        }
        
        self.resting_orders.append(new_order)
        dir_str = "LONG" if direction == 1 else "SHORT"
        print(f"\n[Limit Order Placed] {dir_str} Maker Limit Entry | Price: {limit_price:.4f} | Queue Sz: {resting_size:.2f} | Vol: {vol:.6f}")

    def monitor_resting_orders(self, trade_event, ts_us):
        t_price = float(trade_event["price"])
        t_size = float(trade_event["size"])
        
        # Check running Z-score of velocity of the current bar
        z_velocity = 0.0
        if self.bar_start_time and len(self.bars) > 0 and "velocity_mean" in self.df_features.columns:
            elapsed = (ts_us - self.bar_start_time) / 1000000.0
            curr_velocity = self.cum_vol / elapsed if elapsed > 0 else 0.0
            v_mean = self.df_features.iloc[-1]["velocity_mean"]
            v_std = self.df_features.iloc[-1]["velocity_std"]
            z_velocity = (curr_velocity - v_mean) / (v_std + 1e-6)
            
        for order in list(self.resting_orders):
            # Check cancel/pull due to toxic velocity
            if z_velocity > 2.5:
                print(f"\n[Limit Order Pulled] Toxic velocity spike detected (Z-score: {z_velocity:.2f} > 2.5). Order pulled.")
                self.resting_orders.remove(order)
                continue
                
            # Check cancel due to time expiry
            if ts_us > order["t_cancel"]:
                print(f"\n[Limit Order Expired] 30s cancellation window exceeded. Order expired.")
                self.resting_orders.remove(order)
                continue
                
            # Check fill probability
            filled = False
            if order["direction"] == 1:
                if t_price < order["limit_price"]:
                    filled = True
                elif t_price == order["limit_price"]:
                    if order["resting_size"] == 0.0:
                        filled = True
                    else:
                        order["cum_vol_at_limit"] += t_size
                        if order["cum_vol_at_limit"] >= order["resting_size"]:
                            filled = True
            else:
                if t_price > order["limit_price"]:
                    filled = True
                elif t_price == order["limit_price"]:
                    if order["resting_size"] == 0.0:
                        filled = True
                    else:
                        order["cum_vol_at_limit"] += t_size
                        if order["cum_vol_at_limit"] >= order["resting_size"]:
                            filled = True
                            
            if filled:
                print(f"\n[Limit Order Filled] Maker entry fill at {order['limit_price']:.4f}")
                
                # Active filled trade
                entry_price = order["limit_price"]
                pt_barrier = entry_price * (1 + order["pt_mult"] * order["vol"] * order["direction"])
                sl_barrier = entry_price * (1 - order["sl_mult"] * order["vol"] * order["direction"])
                
                # Maker exit becomes active after maker_latency (200ms for standard, 0ms for premium)
                maker_exit_latency_us = 0 if self.tier == "premium" else 200000
                t_maker_active = ts_us + maker_exit_latency_us
                
                new_trade = {
                    "entry_bar": order["bar_idx"],
                    "direction": order["direction"],
                    "entry_time": ts_us,
                    "entry_price": entry_price,
                    "pt_barrier": pt_barrier,
                    "sl_barrier": sl_barrier,
                    "t_maker_active": t_maker_active,
                    "expiry_bar": order["bar_idx"] + order["hold_bars"],
                    "status": "ACTIVE"
                }
                
                self.active_trades.append(new_trade)
                self.resting_orders.remove(order)

    def monitor_active_trades(self, trade_event):
        t_price = float(trade_event["price"])
        t_time = int(trade_event["transaction_time"])
        
        for trade in list(self.active_trades):
            if trade["status"] != "ACTIVE":
                continue
                
            # Expiry check
            current_bar_idx = self.bar_index
            if current_bar_idx >= trade["expiry_bar"]:
                self.close_trade(trade, t_price, t_time, "TIME_EXPIRY")
                continue
                
            # Stop Loss (Taker)
            if trade["direction"] == 1 and t_price <= trade["sl_barrier"]:
                self.close_trade(trade, trade["sl_barrier"], t_time, "STOP_LOSS")
                continue
            elif trade["direction"] == -1 and t_price >= trade["sl_barrier"]:
                self.close_trade(trade, trade["sl_barrier"], t_time, "STOP_LOSS")
                continue
                
            # Profit Target (Maker - must be active)
            if t_time >= trade["t_maker_active"]:
                if trade["direction"] == 1 and t_price >= trade["pt_barrier"]:
                    self.close_trade(trade, trade["pt_barrier"], t_time, "PROFIT_TARGET")
                elif trade["direction"] == -1 and t_price <= trade["pt_barrier"]:
                    self.close_trade(trade, trade["pt_barrier"], t_time, "PROFIT_TARGET")

    def close_trade(self, trade, fill_price, exit_time, reason):
        trade["status"] = "CLOSED"
        trade["exit_price"] = fill_price
        trade["exit_time"] = exit_time
        trade["exit_reason"] = reason
        
        # Calculate Returns
        raw_return = (fill_price - trade["entry_price"]) / trade["entry_price"] * trade["direction"]
        
        if self.tier == "premium":
            maker_fee = 0.00004
            taker_fee = 0.00028
            slippage = 0.00002
        else:
            maker_fee = 0.0
            taker_fee = 0.0
            slippage = 0.00005
            
        if reason == "PROFIT_TARGET":
            # Maker exit: maker fee on exit, maker fee on entry
            net_return = raw_return - (maker_fee + maker_fee)
        else:
            # Taker exit: taker fee on exit, maker fee on entry, plus slippage
            net_return = raw_return - (maker_fee + taker_fee + slippage)
            
        trade["net_return"] = net_return
        self.completed_trades.append(trade)
        self.active_trades.remove(trade)
        
        # Print summary
        pnl_pct = net_return * 100
        print(f"\n[Trade Closed] Reason: {reason} | Entry: {trade['entry_price']:.4f} | Exit: {fill_price:.4f} | Net PnL: {pnl_pct:+.4f}%")
        self.print_dashboard()

    def print_dashboard(self):
        if not self.completed_trades:
            return
            
        df_closed = pd.DataFrame(self.completed_trades)
        total_pnl = df_closed["net_return"].sum() * 100
        win_rate = (df_closed["net_return"] > 0).mean() * 100
        trade_count = len(df_closed)
        
        print("\n" + "="*50)
        print("          SIMULATED PERFORMANCE DASHBOARD")
        print("="*50)
        print(f"  Pair              : {self.symbol}")
        print(f"  Simulated Trades  : {trade_count}")
        print(f"  Win Rate          : {win_rate:.1f}%")
        print(f"  Cumulative PnL    : {total_pnl:+.4f}%")
        print("="*50 + "\n")

    async def run(self):
        import websockets
        print(f"Connecting to Lighter stream for market {self.symbol}...")
        
        async with websockets.connect(self.uri) as ws:
            # Subscribe to Order Book
            sub_ob = {"type": "subscribe", "channel": f"order_book/{self.market_id}"}
            await ws.send(json.dumps(sub_ob))
            
            # Subscribe to Trades
            sub_trades = {"type": "subscribe", "channel": f"trade/{self.market_id}"}
            await ws.send(json.dumps(sub_trades))
            
            print("WebSocket subscriptions active. Running strategy...")
            
            while True:
                try:
                    msg_str = await ws.recv()
                    msg = json.loads(msg_str)
                    
                    channel = msg.get("channel", "")
                    ts_us = int(msg.get("last_updated_at") or time.time() * 1000000)
                    
                    if "order_book" in channel:
                        ob = msg.get("order_book")
                        if ob:
                            self.update_order_book(ob, ts_us)
                            
                    elif "trade" in channel:
                        trades_list = msg.get("trades") or []
                        liq_list = msg.get("liquidation_trades") or []
                        for t in (trades_list + liq_list):
                            self.handle_trade(t, ts_us)
                            self.monitor_resting_orders(t, ts_us)
                            self.monitor_active_trades(t)
                            
                except Exception as e:
                    print(f"Error in stream loop: {e}", file=sys.stderr)
                    await asyncio.sleep(1)

if __name__ == "__main__":
    market = "1" if len(sys.argv) < 2 else sys.argv[1]
    symbol = "BTC" if len(sys.argv) < 3 else sys.argv[2]
    tier = "premium" if len(sys.argv) < 4 else sys.argv[3]
    
    sim = LiveLighterSimulator(market, symbol, tier=tier)
    
    try:
        asyncio.run(sim.run())
    except KeyboardInterrupt:
        print("\nSimulator stopped by user.")
