# Aggressive Front-Running & Normalized Pull Backtesting Report (V8)

This report presents backtesting results with passive maker limit orders, aggressive front-running queue positioning (one tick improvement when spread > 1 tick), and rolling Z-score velocity-based cancel/pull filters.

## Performance Summary Table

| Pair | Benchmark Return | Std Base Return | Std Base Sharpe | Std Meta Return | Std Meta Sharpe | Prem Base Return | Prem Base Sharpe | Prem Meta Return | Prem Meta Sharpe |
|------|------------------|-----------------|-----------------|-----------------|-----------------|------------------|------------------|------------------|------------------|
| ETH | -4.1433% | -2.4156% | -11.37 | -1.5304% | -63.39 | -8.0987% | -37.69 | +0.4353% | 19.94 |
| BTC | -2.0137% | -2.0045% | -13.66 | -1.8500% | -35.66 | -9.0612% | -61.35 | +0.2341% | 27.69 |
| SOL | -2.7012% | -3.7154% | -32.09 | -0.3372% | -23.73 | -4.4318% | -36.24 | +0.0369% | 3.91 |
