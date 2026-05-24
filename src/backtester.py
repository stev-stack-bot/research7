import pandas as pd
import numpy as np

def apply_triple_barriers(df, pt_mult=3.0, sl_mult=1.0, hold_bars=15, z_threshold=2.0, execution_mode="maker"):
    """
    Apply Triple Barrier Method to generate labels for primary entry signals.
    df: DataFrame containing close prices, volatility, timestamps, and bid/ask fields if maker.
    Returns a DataFrame of trade events with columns:
      - entry_idx: index of entry bar (when filled)
      - signal_idx: index of signal bar
      - entry_price: price at entry
      - direction: 1 for Long, -1 for Short
      - exit_idx: index of exit bar
      - exit_price: price at exit
      - exit_type: 'pt' for profit target, 'sl' for stop loss, 'time' for time barrier
      - raw_return: gross trade return
      - label: 1 if profitable (hit pt first), 0 otherwise (hit sl or vertical barrier first)
    """
    events = []
    
    # In maker mode, we need at least one subsequent bar for entry check, so range up to len(df) - 1
    max_idx = len(df) - 1 if execution_mode == "maker" else len(df)
    
    for idx in range(max_idx):
        # Primary signal checks
        cofi_z = df.loc[idx, "cofi_z"]
        if cofi_z >= z_threshold:
            direction = 1  # Long
        elif cofi_z <= -z_threshold:
            direction = -1  # Short
        else:
            continue
            
        signal_idx = idx
        vol = df.loc[signal_idx, "volatility"]
        
        if execution_mode == "taker":
            entry_idx = signal_idx
            entry_price = df.loc[entry_idx, "close"]
            filled = True
        else: # maker mode
            # Place limit order at bid (for Long) or ask (for Short) of the signal bar close
            limit_price = df.loc[signal_idx, "bid"] if "bid" in df.columns else df.loc[signal_idx, "close"]
            if direction == -1:
                limit_price = df.loc[signal_idx, "ask"] if "ask" in df.columns else df.loc[signal_idx, "close"]
            
            # Check if filled on the next bar (idx + 1)
            entry_idx = idx + 1
            low_k = df.loc[entry_idx, "low"]
            high_k = df.loc[entry_idx, "high"]
            
            if direction == 1: # Long entry
                # Filled if low is strictly below limit price (crossed the touch)
                if low_k < limit_price:
                    entry_price = limit_price
                    filled = True
                else:
                    filled = False
            else: # Short entry
                # Filled if high is strictly above limit price
                if high_k > limit_price:
                    entry_price = limit_price
                    filled = True
                else:
                    filled = False
                    
        if not filled:
            continue
            
        pt_barrier = entry_price * (1 + pt_mult * vol * direction)
        sl_barrier = entry_price * (1 - sl_mult * vol * direction)
        
        exit_idx = min(entry_idx + hold_bars, len(df) - 1)
        exit_price = df.loc[exit_idx, "close"]
        exit_type = "time"
        label = 0
        
        start_search_idx = entry_idx if execution_mode == "maker" else entry_idx + 1
        
        # Search for first barrier breach
        for k in range(start_search_idx, exit_idx + 1):
            curr_low = df.loc[k, "low"]
            curr_high = df.loc[k, "high"]
            
            if direction == 1: # Long
                # Check Stop Loss first (conservative)
                if curr_low <= sl_barrier:
                    exit_idx = k
                    exit_price = sl_barrier
                    exit_type = "sl"
                    label = 0
                    break
                elif curr_high >= pt_barrier:
                    exit_idx = k
                    exit_price = pt_barrier
                    exit_type = "pt"
                    label = 1
                    break
            else: # Short
                # Check Stop Loss first (conservative)
                if curr_high >= sl_barrier:
                    exit_idx = k
                    exit_price = sl_barrier
                    exit_type = "sl"
                    label = 0
                    break
                elif curr_low <= pt_barrier:
                    exit_idx = k
                    exit_price = pt_barrier
                    exit_type = "pt"
                    label = 1
                    break
                    
        raw_ret = (exit_price - entry_price) / entry_price * direction
        
        events.append({
            "entry_idx": entry_idx,
            "signal_idx": signal_idx,
            "entry_time": df.loc[entry_idx, "end_time"],
            "direction": direction,
            "exit_idx": exit_idx,
            "exit_time": df.loc[exit_idx, "end_time"],
            "entry_price": entry_price,
            "exit_price": exit_price,
            "exit_type": exit_type,
            "raw_return": raw_ret,
            "label": label
        })
        
    return pd.DataFrame(events)

def simulate_backtest(df, events_df, maker_fee=0.00015, taker_fee=0.00045, slippage=0.0001, meta_model=None, prob_thresh=0.55):
    """
    Run trading simulation and apply transaction costs.
    If meta_model is provided, filter trades based on classification probability.
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
        # Feature extraction should use signal_idx if present, else entry_idx
        feat_idx = int(row["signal_idx"]) if "signal_idx" in row else int(row["entry_idx"])
        
        # Meta-labeling check
        execute = True
        if meta_model is not None:
            # Extract features for the decision bar
            features = np.array([[
                df.loc[feat_idx, "volatility_ratio"],
                df.loc[feat_idx, "duration"],
                df.loc[feat_idx, "depth_ratio"]
            ]])
            prob_probs = meta_model.predict_proba(features)[0]
            prob = prob_probs[1] if len(prob_probs) > 1 else (1.0 if meta_model.classes_[0] == 1 else 0.0)
            if prob < prob_thresh:
                execute = False
                
        if execute:
            # Apply appropriate fees and slippage based on exit type
            exit_type = row.get("exit_type", "taker_taker")
            if exit_type == "pt":
                # maker entry, maker exit
                cost = maker_fee + maker_fee
            elif exit_type in ["sl", "time"]:
                # maker entry, taker exit
                cost = maker_fee + taker_fee + slippage
            else:
                # default taker-taker
                cost = (taker_fee + slippage) * 2
                
            net_return = row["raw_return"] - cost
            trades.append({
                "entry_idx": int(row["entry_idx"]),
                "signal_idx": feat_idx,
                "direction": row["direction"],
                "exit_idx": int(row["exit_idx"]),
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
    
    # Sharpe Ratio (daily equivalent approximated from bar counts)
    mean_ret = t_df["net_return"].mean()
    std_ret = t_df["net_return"].std()
    sharpe = (mean_ret / std_ret * np.sqrt(252 * 100)) if std_ret > 0 else 0.0
    
    # Max Drawdown calculation
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
