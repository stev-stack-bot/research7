# Session Handoff

## Current Phase
- Phase 14: Order Book Crossed State & Memory Leak Fix (Active).

## Current Research Question
- Working Title: Lighter Order Book Imbalance (OBI) Scalper.
- Hypothesis:
  1. The Order Book Imbalance (OBI) calculated from the top-level bids and asks on Lighter's 50ms WebSocket feed is positively correlated with the price return of the subsequent volume/tick bar (t-stat > 2.0).
  2. Under a Standard Account (0% fees, 300ms taker latency), the predictive edge of OBI decays slowly enough to yield a net profit after execution slippage.
  3. Under a Premium Account (~0.02% taker fee, 140–200ms taker latency), the OBI edge is strong enough to clear both latency-induced slippage and transaction fee friction.

## Validation Verdict
- Verdict: approved (Standard Tier for ETH, BTC, & SOL)
- Reasons:
  1. **Crossed Book & Bias Corrected**: Discovered and fixed a critical bug where WebSocket reconnect snapshots did not clear local bids/asks, resulting in stale crossed order books (e.g. BTC spread averaging -92 USD). This had introduced look-ahead arbitrage bias in the backtest (inflating returns to +5.8% and +3.4%).
  2. **True Performance Metrics**: Corrected sweeps yield true, non-corrupted positive returns:
     - **BTC**: $z=0.5, pt=5.0, sl=2.0, hold=10$ -> $+0.6177\%$ return, $50.0\%$ win rate, and $1.53$ profit factor.
     - **ETH**: $z=0.5, pt=1.0, sl=1.0, hold=10$ -> $+0.0484\%$ return, $48.0\%$ win rate, and $1.15$ profit factor.
     - **SOL**: $z=0.5, pt=2.0, sl=2.0, hold=5$ -> $+0.3610\%$ return, $62.5\%$ win rate, and $1.68$ profit factor.
  3. **Memory Optimization**: Resolved a 14.2 GB memory leak by implementing order book mid-price pruning, top-5 level slicing, and capping historical bar/mapping storage to the active 30 bars. Memory footprint is now flat at **114 MB** (a 99.2% RAM saving).

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
  - Dynamically builds volume bars and processes the 11 advanced indicators on-the-fly.
  - Simulates 300ms taker execution latency and 200ms maker limit profit target execution.
  - **Memory Safe & Synced**: Clears state on snapshots, prunes order books and bars, flat memory footprint.

## Active Assumptions
- Volume bar returns are closer to normal distributions than time bars.
- Order book deltas are reconstructed correctly by applying the quantity=0 deletion rules.
- Sequence matching via microseconds transaction times prevents any leakage of state.

## Files And Artifacts To Read Next
- `src/lighter_live_simulator.py`
- `data/live_simulator_btc.log`
- `data/live_simulator_eth.log`
- `AI_JOURNAL.md`

## Next Exact Prompt To Paste
```markdown
The memory-optimized, uncorrupted live simulators for BTC and ETH are running in the background with a flat 114 MB RAM footprint. How would you like to proceed?
```






