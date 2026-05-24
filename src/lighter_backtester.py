import pandas as pd
import numpy as np
from bisect import bisect_left

def apply_lighter_triple_barriers(df, book_states, trade_events, pt_mult=3.0, sl_mult=1.0, hold_bars=10, z_threshold=1.5, latency_ms=300, maker_latency_ms=200):
    """
    Apply Triple Barrier Method to Lighter data.
    - entries: taker market order executed at t_close + latency_ms
    - profit target (PT): maker limit order active at t_entry_exec + maker_latency_ms
    - stop loss (SL): taker order filled at t_trigger + latency_ms
    - time barrier: taker order filled at t_expiry + latency_ms
    """
    events = []
    
    book_times = [s["time"] for s in book_states]
    trade_times = [t["transaction_time"] for t in trade_events]
    
    for idx, row in df.iterrows():
        cofi_z = row["cofi_z"]
        if cofi_z >= z_threshold:
            direction = 1  # Long
        elif cofi_z <= -z_threshold:
            direction = -1  # Short
        else:
            continue
            
        signal_time = row["end_time"]
        vol = row["volatility"]
        
        # Calculate execution time for entry taker order
        t_entry_exec = signal_time + latency_ms * 1000
        
        # Look up best price in book at t_entry_exec
        book_idx = bisect_left(book_times, t_entry_exec)
        if book_idx >= len(book_states):
            continue
            
        entry_book = book_states[book_idx]
        if direction == 1:
            if not entry_book["asks"]:
                continue
            entry_price = float(entry_book["asks"][0]["px"])
        else:
            if not entry_book["bids"]:
                continue
            entry_price = float(entry_book["bids"][0]["px"])
            
        # Find entry bar index
        entry_bar_series = df[(df["start_time"] <= t_entry_exec) & (t_entry_exec <= df["end_time"])]
        if entry_bar_series.empty:
            if t_entry_exec > df["end_time"].max():
                continue
            entry_idx = idx
        else:
            entry_idx = int(entry_bar_series.iloc[0]["bar_index"])
            
        # Set barriers
        pt_barrier = entry_price * (1 + pt_mult * vol * direction)
        sl_barrier = entry_price * (1 - sl_mult * vol * direction)
        
        # Limit order becomes active at t_maker_active
        t_maker_active = t_entry_exec + maker_latency_ms * 1000
        
        # Time expiry barrier
        expiry_bar_idx = min(entry_idx + hold_bars, len(df) - 1)
        t_expiry = df.loc[expiry_bar_idx, "end_time"]
        
        # Search subsequent trade events for barriers
        first_trade_idx = bisect_left(trade_times, t_entry_exec)
        
        exit_time = t_expiry
        exit_type = "time"
        
        for k in range(first_trade_idx, len(trade_events)):
            trade = trade_events[k]
            t_trade = trade["transaction_time"]
            if t_trade > t_expiry:
                break
                
            p_trade = trade["price"]
            
            # Check Stop Loss first (conservative)
            if direction == 1 and p_trade <= sl_barrier:
                exit_time = t_trade
                exit_type = "sl"
                break
            elif direction == -1 and p_trade >= sl_barrier:
                exit_time = t_trade
                exit_type = "sl"
                break
                
            # Check Profit Target (maker order must be active)
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
            exit_book_idx = bisect_left(book_times, t_trigger_exec)
            if exit_book_idx < len(book_states):
                exit_book = book_states[exit_book_idx]
                if direction == 1:
                    exit_price = float(exit_book["bids"][0]["px"]) if exit_book["bids"] else sl_barrier
                else:
                    exit_price = float(exit_book["asks"][0]["px"]) if exit_book["asks"] else sl_barrier
            else:
                exit_price = sl_barrier
        else:
            t_expiry_exec = t_expiry + latency_ms * 1000
            exit_book_idx = bisect_left(book_times, t_expiry_exec)
            if exit_book_idx < len(book_states):
                exit_book = book_states[exit_book_idx]
                if direction == 1:
                    exit_price = float(exit_book["bids"][0]["px"]) if exit_book["bids"] else df.loc[expiry_bar_idx, "close"]
                else:
                    exit_price = float(exit_book["asks"][0]["px"]) if exit_book["asks"] else df.loc[expiry_bar_idx, "close"]
            else:
                exit_price = df.loc[expiry_bar_idx, "close"]
                
        # Find which bar contains exit_time
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

def simulate_lighter_backtest(df, events_df, maker_fee=0.0, taker_fee=0.0, slippage=0.0, meta_model=None, prob_thresh=0.55):
    """
    Run backtest simulation applying cost structure (maker/taker) and slippage.
    """
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
            FEATURE_COLS = [
                "volatility_ratio", "duration", "depth_ratio", 
                "cofi_l1_z", "micro_ret", "avg_spread", "vpin", 
                "ret_lag1", "ret_lag2", "depth_ratio_l3", "depth_ratio_l5"
            ]
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
