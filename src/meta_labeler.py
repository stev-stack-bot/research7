import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

def purge_and_embargo(df, events_df, train_start_idx, train_end_idx, val_start_idx, embargo_pct=0.01):
    """
    Remove training events that overlap with validation/test periods or fall in the embargo window.
    embargo_pct: fraction of training data to drop as embargo buffer after validation boundary.
    """
    if events_df.empty:
        return events_df
        
    # Chronological partition of events
    train_events = events_df[
        (events_df["entry_idx"] >= train_start_idx) & 
        (events_df["entry_idx"] <= train_end_idx)
    ].copy()
    
    val_events = events_df[
        (events_df["entry_idx"] >= val_start_idx)
    ].copy()
    
    if train_events.empty or val_events.empty:
        return train_events
        
    # Purging: delete training events whose exit index is after or equal to validation entry start
    val_min_entry = val_events["entry_idx"].min()
    purged_events = train_events[train_events["exit_idx"] < val_min_entry].copy()
    
    # Embargo: drop a buffer window of events immediately preceding validation start
    embargo_size = int(len(df) * embargo_pct)
    embargo_boundary = val_min_entry - embargo_size
    final_train_events = purged_events[purged_events["entry_idx"] < embargo_boundary].copy()
    
    return final_train_events

def train_meta_labeler(df, train_events):
    """
    Train a Random Forest classifier using non-leaky features.
    """
    if train_events.empty:
        raise ValueError("Training events DataFrame is empty. Cannot train meta-labeler.")
        
    X_train = []
    y_train = []
    
    for idx, row in train_events.iterrows():
        entry_idx = int(row["entry_idx"])
        X_train.append([
            df.loc[entry_idx, "volatility_ratio"],
            df.loc[entry_idx, "duration"],
            df.loc[entry_idx, "depth_ratio"]
        ])
        y_train.append(int(row["label"]))
        
    X_train = np.array(X_train)
    y_train = np.array(y_train)
    
    # Simple, robust random forest to avoid overfitting
    model = RandomForestClassifier(n_estimators=50, max_depth=3, random_state=42)
    model.fit(X_train, y_train)
    
    return model
