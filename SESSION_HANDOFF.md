# Session Handoff

## Current Phase
- Phase 18: V8 Queue Front-Running & Rolling Z-Score Pull Signal (Deployed).

## Current Research Question
- Working Title: Lighter Passive Maker Scalper (V8).
- Hypothesis:
  1. Stepping one tick inside the spread (`spread > tick_size * 1.001`) grants instant queue priority and bypasses the touch penalty.
  2. Canceling resting limit entries when the running bar velocity Z-score exceeds `2.5` shields the strategy from adverse selection and toxic volume sweeps.
  3. Real-time inference using trained Random Forest meta-labeler veto models reduces variance and locks in positive net returns under premium fees.

## Validation Verdict
- Verdict: Deployed to background live simulators (Premium Tiers for ETH, BTC, & SOL)
- Reasons:
  1. **V8 Live Simulator Deployed**: `src/lighter_live_simulator.py` upgraded to passive maker limit entries, queue depth clearance tracking, dynamic Z-score velocity cancels, and real-time Random Forest meta-labeler inference.
  2. **Simulator Status**: Stopped (PIDs terminated at user request).

## Lighter Data Export Tool
- **Script**: `src/export_lighter_data.py`
- **Features**:
  - Automatically scans for your Lighter `account_index` using the public key in `.env`.
  - Generates secure authentication tokens offline using the Lighter Go signer shared library.
  - Triggers `/api/v1/export` REST call to export trade and funding logs.

## Lighter Live Simulator
- **Script**: `src/lighter_live_simulator.py`
- **Features**:
  - Connects to Lighter's live WebSocket feed and reconstructs the L2 book in real-time.
  - Dynamically builds volume bars and processes the 14 V8 indicators on-the-fly.
  - Loaded Random Forest veto classifiers (`models/prem_model_{symbol}.joblib`) to filter signals.
  - Tracks limit queue depth fills and executes rolling Z-score velocity cancellations.

## Active Assumptions
- Volume bar returns are closer to normal distributions than time bars.
- Order book deltas are reconstructed correctly by applying the quantity=0 deletion rules.
- Sequence matching via microseconds transaction times prevents any leakage of state.

## Files And Artifacts To Read Next
- `data/live_simulator_btc.log`
- `data/live_simulator_eth.log`
- `data/live_simulator_sol.log`
- `deploy_simulators.sh`
- `AI_JOURNAL.md`

## Next Steps
- Wait for a larger dataset (e.g. weekly/monthly data export) to run extended V8 maker backtests.

