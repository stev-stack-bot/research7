import asyncio
import json
import os
import sys
import time
import numpy as np
import pandas as pd
from bisect import bisect_left

# Add src to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.lighter_features import compute_ofi_delta

class LiveLighterSimulator:
    def __init__(self, market_id="1", symbol="BTC", z_threshold=0.1, pt_mult=5.0, sl_mult=2.0, hold_bars=10):
        self.market_id = str(market_id)
        self.symbol = symbol
        self.z_threshold = float(z_threshold)
        self.pt_mult = float(pt_mult)
        self.sl_mult = float(sl_mult)
        self.hold_bars = int(hold_bars)
        
        self.uri = "wss://mainnet.zklighter.elliot.ai/stream?readonly=true"
        
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
        
        # Volume bar threshold (matched to optimized backtest sizes)
        if symbol == "BTC":
            self.v_thresh = 3.43
        elif symbol == "ETH":
            self.v_thresh = 78.4
        elif symbol == "SOL":
            self.v_thresh = 513.8
        else:
            self.v_thresh = 100.0

        
        # Strategy execution state
        self.active_trades = [] # List of active trade dicts
        self.completed_trades = []
        self.df_features = pd.DataFrame()
        self.book_bar_mapping = []
        
        print(f"=======================================================")
        print(f"       LIGHTER REAL-TIME STRATEGY SIMULATOR")
        print(f"=======================================================")
        print(f"  Target Market: {self.symbol} (ID: {self.market_id})")
        print(f"  Parameters   : z_thresh={self.z_threshold}, pt_mult={self.pt_mult}, sl_mult={self.sl_mult}, hold_bars={self.hold_bars}")
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
            if len(self.bars) > 30:
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
        # Warm up for at least 12 bars to ensure rolling windows (window=10) are fully populated and stable
        if len(self.bars) < 12:
            return
            
        bars_df = pd.DataFrame(self.bars)
        
        # Calculate features using z_window = 10 (short window for live display)
        try:
            from src.lighter_features import compute_lighter_bar_features
            df_feats = compute_lighter_bar_features(
                bars_df, self.book_bar_mapping, self.recent_trades, levels_count=5, z_window=10
            )
            self.df_features = df_feats
        except Exception as e:
            print(f"Error computing features: {e}")
            return
            
        latest_row = df_feats.iloc[-1]
        cofi_z = latest_row["cofi_z"]
        vpin = latest_row["vpin"]
        spread = latest_row["avg_spread"]
        
        # Compute rolling spread mean
        rolling_spread_mean = df_feats["avg_spread"].rolling(10, min_periods=1).mean().iloc[-1]
        
        print(f"    Features -> OBI Z-Score: {cofi_z:.4f} | VPIN: {vpin:.4f} | Spread: {spread:.4f} (Mean: {rolling_spread_mean:.4f})")
        
        # Signal Generation
        direction = 0
        if cofi_z >= self.z_threshold:
            direction = 1
        elif cofi_z <= -self.z_threshold:
            direction = -1
            
        if direction != 0:
            # Apply Filters:
            # 1. Spread filter: Current spread must be <= rolling mean spread to minimize entry slippage
            # 2. VPIN filter: Current VPIN must be <= 0.6 to avoid toxic order flow
            if spread > rolling_spread_mean:
                print(f"    [Signal Filtered] Spread too wide: {spread:.4f} > mean {rolling_spread_mean:.4f}")
                direction = 0
            elif vpin > 0.6:
                print(f"    [Signal Filtered] VPIN too high (toxic flow): {vpin:.4f} > 0.6")
                direction = 0
                
        if direction != 0:
            self.trigger_simulated_trade(direction, latest_row)

    def trigger_simulated_trade(self, direction, bar_row):
        signal_time = bar_row["end_time"]
        vol = bar_row["volatility"]
        
        # Simulate execution latency (300ms in microseconds = 300,000)
        t_exec = signal_time + 300000
        
        # Schedule the fill logic to execute after latency
        asyncio.create_task(self.fill_trade_after_latency(direction, t_exec, vol, bar_row["bar_index"]))

    async def fill_trade_after_latency(self, direction, t_exec, vol, bar_idx):
        # Wait 300ms in real-world time to mimic market arrival
        await asyncio.sleep(0.3)
        
        # Find order book price at t_exec
        book_times = [b["time"] for b in self.book_history]
        if not book_times:
            return
            
        idx = bisect_left(book_times, t_exec)
        if idx >= len(self.book_history):
            idx = len(self.book_history) - 1
            
        book = self.book_history[idx]
        
        # Entry price (taker fill)
        if direction == 1:
            if not book["asks"]: return
            entry_price = float(book["asks"][0]["px"])
        else:
            if not book["bids"]: return
            entry_price = float(book["bids"][0]["px"])
            
        # Target barriers
        pt_barrier = entry_price * (1 + self.pt_mult * vol * direction)
        sl_barrier = entry_price * (1 - self.sl_mult * vol * direction)
        
        # Maker limit profit target becomes active 200ms after entry fill
        t_maker_active = t_exec + 200000
        
        new_trade = {
            "entry_bar": bar_idx,
            "direction": direction,
            "entry_time": t_exec,
            "entry_price": entry_price,
            "pt_barrier": pt_barrier,
            "sl_barrier": sl_barrier,
            "t_maker_active": t_maker_active,
            "expiry_bar": bar_idx + self.hold_bars,
            "status": "ACTIVE"
        }
        
        self.active_trades.append(new_trade)
        dir_str = "LONG" if direction == 1 else "SHORT"
        print(f"\n[Strategy Trade Triggered] {dir_str} Entry | Fill Price: {entry_price:.2f} | TP: {pt_barrier:.2f} | SL: {sl_barrier:.2f}")

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
        
        # Calculate Returns (Taker entry, Maker exit if TP, Taker if SL/Time)
        slippage = 0.00005 # 0.5 bps
        raw_return = (fill_price - trade["entry_price"]) / trade["entry_price"] * trade["direction"]
        
        if reason == "PROFIT_TARGET":
            # Maker exit: 0% fee
            net_return = raw_return - slippage
        else:
            # Taker exit: 0% fee, double slippage
            net_return = raw_return - (slippage * 2)
            
        trade["net_return"] = net_return
        self.completed_trades.append(trade)
        self.active_trades.remove(trade)
        
        # Print summary
        pnl_pct = net_return * 100
        print(f"\n[Trade Closed] Reason: {reason} | Entry: {trade['entry_price']:.2f} | Exit: {fill_price:.2f} | Net PnL: {pnl_pct:+.4f}%")
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
                            self.monitor_active_trades(t)
                            
                except Exception as e:
                    print(f"Error in stream loop: {e}", file=sys.stderr)
                    await asyncio.sleep(1)

if __name__ == "__main__":
    market = "1" if len(sys.argv) < 2 else sys.argv[1]
    symbol = "BTC" if len(sys.argv) < 3 else sys.argv[2]
    
    # Use best parameters found in grid search on 1-hour dataset
    if symbol == "BTC":
        z_t = 0.5; pt = 5.0; sl = 2.0; hold = 10
    elif symbol == "SOL":
        z_t = 0.5; pt = 2.0; sl = 2.0; hold = 5
    elif symbol == "ETH":
        z_t = 0.5; pt = 1.0; sl = 1.0; hold = 10
    else:
        z_t = 0.5; pt = 2.0; sl = 2.0; hold = 5
        
    sim = LiveLighterSimulator(market, symbol, z_threshold=z_t, pt_mult=pt, sl_mult=sl, hold_bars=hold)
    
    try:
        asyncio.run(sim.run())
    except KeyboardInterrupt:
        print("\nSimulator stopped by user.")
