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
        
        # Dynamic volume bar threshold (initial guess, updated dynamically)
        self.v_thresh = 1.0 if symbol == "BTC" else 100.0
        
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
                
        sorted_bids = sorted([{"px": p, "sz": s} for p, s in self.bids.items()], key=lambda x: x["px"], reverse=True)
        sorted_asks = sorted([{"px": p, "sz": s} for p, s in self.asks.items()], key=lambda x: x["px"])
        
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
            print(f"\n[+] Volume Bar {self.bar_index} Formed | Close: {bar_close:.2f} | Vol: {self.cum_vol:.3f} | Trades: {len(bar_trades)}")
            
            # Map book updates to this bar
            for state in self.book_history:
                if self.bar_start_time <= state["time"] <= bar_end_time:
                    self.book_bar_mapping.append((self.bar_index, state))
                    
            # Compute features & check signals
            self.process_features_and_signals()
            
            # Reset for next bar
            self.cum_vol = 0.0
            self.bar_start_idx = len(self.recent_trades)
            self.bar_start_time = None
            self.bar_index += 1
            
            # Keep trade history under control
            if len(self.recent_trades) > 5000:
                self.recent_trades = self.recent_trades[-1000:]
                self.bar_start_idx = len(self.recent_trades)

    def process_features_and_signals(self):
        if len(self.bars) < 3:
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
        
        print(f"    Features -> OBI Z-Score: {cofi_z:.4f} | VPIN: {vpin:.4f} | Spread: {spread:.4f}")
        
        # Signal Generation
        direction = 0
        if cofi_z >= self.z_threshold:
            direction = 1
        elif cofi_z <= -self.z_threshold:
            direction = -1
            
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
                    
                    m_type = msg.get("type")
                    if not m_type:
                        continue
                        
                    ts_us = int(msg.get("last_updated_at") or time.time() * 1000000)
                    
                    if m_type == "update/order_book" or m_type.startswith("subscribed/"):
                        ob = msg.get("order_book")
                        if ob:
                            self.update_order_book(ob, ts_us)
                            
                    elif m_type == "update/trade":
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
    
    # Use best parameters found in grid search
    if symbol == "BTC":
        z_t = 0.1; pt = 5.0; sl = 2.0; hold = 10
    elif symbol == "SOL":
        z_t = 1.0; pt = 3.0; sl = 2.0; hold = 10
    else:
        z_t = 0.5; pt = 2.0; sl = 1.0; hold = 5
        
    sim = LiveLighterSimulator(market, symbol, z_threshold=z_t, pt_mult=pt, sl_mult=sl, hold_bars=hold)
    
    try:
        asyncio.run(sim.run())
    except KeyboardInterrupt:
        print("\nSimulator stopped by user.")
