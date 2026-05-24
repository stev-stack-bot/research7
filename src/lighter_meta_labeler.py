import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

def purge_and_embargo_lighter(df, events_df, train_start_idx, train_end_idx, val_start_idx, embargo_pct=0.01):
    """
    Remove training events that overlap with validation/test periods or fall in the embargo window.
    """
    if events_df.empty:
        return events_df
        
    train_events = events_df[
        (events_df["entry_idx"] >= train_start_idx) & 
        (events_df["entry_idx"] <= train_end_idx)
    ].copy()
    
    val_events = events_df[
        (events_df["entry_idx"] >= val_start_idx)
    ].copy()
    
    if train_events.empty or val_events.empty:
        return train_events
        
    val_min_entry = val_events["entry_idx"].min()
    purged_events = train_events[train_events["exit_idx"] < val_min_entry].copy()
    
    embargo_size = int(len(df) * embargo_pct)
    embargo_boundary = val_min_entry - embargo_size
    final_train_events = purged_events[purged_events["entry_idx"] < embargo_boundary].copy()
    
    return final_train_events

def train_lighter_meta_labeler(df, train_events):
    """
    Train a Random Forest classifier using enriched microstructural features.
    """
    if train_events.empty:
        raise ValueError("Training events DataFrame is empty. Cannot train meta-labeler.")
        
    FEATURE_COLS = [
        "volatility_ratio", "duration", "depth_ratio", 
        "cofi_l1_z", "micro_ret", "avg_spread", "vpin", 
        "ret_lag1", "ret_lag2", "depth_ratio_l3", "depth_ratio_l5"
    ]
    
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

