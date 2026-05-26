# Advanced Multi-Pair Backtesting Report (14-Hour Dataset)

This report presents the backtesting results of the OBI Scalper strategy with 6 new microstructural features and a 2x2 comparison of signal filtering and machine learning.

## Standard Tier Performance Summary Table (0% fees, 300ms taker / 200ms maker latency)

| Pair | Benchmark Return | Baseline Return (No Filt, No ML) | Baseline PF | Filtered Return (Filt, No ML) | Filtered PF | Meta-Labeled (No Filt, ML) | Meta-Labeled PF | Combined Return (Filt, ML) | Combined PF |
|------|------------------|----------------------------------|-------------|------------------------------|-------------|----------------------------|-----------------|----------------------------|-------------|
| ETH | 0.3930% | -0.6340% | 0.84 | -0.8207% | 0.78 | -0.4965% | 0.63 | +0.1575% | 1.16 |
| BTC | 0.2151% | -3.4004% | 0.51 | -2.7458% | 0.53 | -0.1074% | 0.00 | +0.0000% | 0.00 |
| SOL | 0.6219% | -2.1458% | 0.67 | -2.1227% | 0.66 | -0.3170% | 0.65 | -0.9975% | 0.28 |

## Premium Tier Performance Summary Table (2.8 bps taker / 0.4 bps maker, 140ms taker latency)

| Pair | Benchmark Return | Baseline Return (No Filt, No ML) | Baseline PF | Filtered Return (Filt, No ML) | Filtered PF | Meta-Labeled (No Filt, ML) | Meta-Labeled PF | Combined Return (Filt, ML) | Combined PF |
|------|------------------|----------------------------------|-------------|------------------------------|-------------|----------------------------|-----------------|----------------------------|-------------|
| ETH | 0.3930% | -6.2170% | 0.16 | -5.9551% | 0.15 | -1.9032% | 0.16 | -1.4165% | 0.23 |
| BTC | 0.2151% | -11.7110% | 0.13 | -9.5202% | 0.14 | -0.2719% | 0.00 | +0.0524% | inf |
| SOL | 0.6219% | -6.5535% | 0.33 | -6.2120% | 0.32 | -1.5998% | 0.15 | -1.6709% | 0.20 |
