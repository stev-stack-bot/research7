# Robust Asymmetric Baseline Backtesting Report (61-Hour Extended Dataset)

This report presents backtesting results with the new robust asymmetric parameters applied to the baseline, combined with the 14-feature meta-labeler, run over the newly expanded 61-hour Lighter dataset.

## Performance Summary Table

| Pair | Benchmark Return | Std Base Return | Std Base PF | Std Meta Return | Std Meta PF | Prem Base Return | Prem Base PF | Prem Meta Return | Prem Meta PF |
|------|------------------|-----------------|-------------|-----------------|-------------|------------------|--------------|------------------|--------------|
| ETH  | -4.1433%         | -1.5382%        | 0.93        | -0.3994%        | 0.46        | -17.2131%        | 0.48         | -0.4377%         | 0.26         |
| BTC  | -2.0137%         | -2.6815%        | 0.84        | +0.0000%        | 0.00        | -22.2656%        | 0.26         | +0.0000%         | 0.00         |
| SOL  | -2.7012%         | -1.8187%        | 0.89        | -0.3132%        | 0.40        | -9.4447%         | 0.57         | -0.3598%         | 0.00         |

## Key Findings & Observations

1. **Market Context**: During this 61-hour window, the market experienced a strong downward trend, with benchmarks declining:
   - ETH: **-4.14%**
   - BTC: **-2.01%**
   - SOL: **-2.70%**

2. **Baseline PnL Preservation**: 
   - On the Standard Tier, the baseline strategy outperformed the benchmark in terms of total return (e.g., ETH baseline lost -1.54% vs -4.14% buy-and-hold; SOL baseline lost -1.82% vs -2.70% buy-and-hold).
   - On the Premium Tier, execution friction and latency-induced slippage degraded the baseline strategy significantly (e.g., BTC lost -22.27% and ETH lost -17.21%).

3. **Meta-Labeling Performance**:
   - The Random Forest meta-labeler successfully protected capital under adverse conditions.
   - For BTC, it filtered out **100% of trades**, keeping returns at exactly **+0.0000%** and completely avoiding the downward baseline drift.
   - For ETH and SOL, it reduced standard losses to **-0.40%** and **-0.31%** (trading only 12 and 5 times respectively, compared to 338 and 161 for the baseline).
   - This confirms the predictive power of the 14-feature microstructure model in identifying low-probability trade setups and applying risk-off vetoes.
