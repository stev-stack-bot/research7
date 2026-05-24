# Phase 04 Prompt: Backtest Design

Design the backtest before implementation. The goal is to make the execution model explicit and prevent accidental curve fitting.

## Read First

Read:

- `SESSION_HANDOFF.md`
- Latest relevant `AI_JOURNAL.md` entries.
- Phase 01 research question/spec.
- Phase 02 data audit result.
- Phase 03 signal specification.
- Existing backtest engine, config, metrics, and test files/notebooks if present.

## Previous-State Dependency

Begin by summarizing:

- Hypothesis and signal rules.
- Data constraints.
- Leakage controls.
- Invalidation criteria.

## Allowed Actions

You may:

- Define execution timing, fees, slippage, liquidity filters, sizing, risk constraints, benchmark, and metrics.
- Define train/validation/test split and parameter policy.
- Inspect existing backtest utilities.
- Recommend implementation tasks for Phase 05.

You must not:

- Implement code.
- Run strategy optimization.
- Select parameters by maximizing performance.
- Drop bad periods without predeclared rationale.
- Move toward paper/live trading.

## Required Output

Return:

```markdown
## Backtest Design
- Engine or approach:
- Bar type & frequency: (e.g., standard time candles, volume/dollar bars aggregated from ticks)
- Decision time: (e.g., bar close, next trade tick)
- Execution time: (e.g., limit order at bar close, execution on next trade/bar start)
- Order model:
- Fee model:
- Slippage model:
- Liquidity/capacity constraint:
- Position sizing & Meta-Labeling: (how the meta-labeling probability or prediction scales position sizing or filters trades; check that baseline primary strategy meets the scorecard requirements before scaling)
- Rebalancing:
- Risk constraints:
- Benchmark:
- Baselines: (e.g., primary strategy alone without meta-labeling, buy-and-hold)
- Metrics:
- Train/validation/test split:
- Purging and Embargo rules: (for cross-validation and split testing of meta-labeling model)
- Parameter policy:
- Invalidation thresholds:

## Implementation Contract
- Files/notebooks likely to change/create:
- Required tests/checks:
- Required output artifacts:
- Definition of done for Phase 05:

## Phase Closeout
- Phase: 04 Backtest Design
- Status: complete | blocked | needs human decision
- Files inspected:
- Files changed:
- Commands/checks run:
- Key evidence:
- Assumptions:
- Failures or risks:
- Journal updated: yes | no, why
- Handoff updated: yes | no, why
- Next recommended phase:
- Copy-paste next prompt:
```

## Journal Command

Append a dated `AI_JOURNAL.md` entry with the execution model, costs, metrics, split policy, and implementation contract.

## Handoff Command

Update `SESSION_HANDOFF.md` with the backtest design summary, validation gates, implementation contract, and the exact Phase 05 prompt to paste.

