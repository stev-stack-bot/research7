# Phase 06 Prompt: Validation

Validate the research result. Treat all promising performance as untrusted until the gates below are checked.

## Read First

Read:

- `SESSION_HANDOFF.md`
- Latest relevant `AI_JOURNAL.md` entries.
- Phase 01 through Phase 05 specs and implementation notes.
- Relevant code, tests, output artifacts, logs, metrics, and plots.

## Previous-State Dependency

Begin by summarizing:

- Implemented behavior.
- Backtest design.
- Required validation gates.
- Known failures or deviations from Phase 05.

## Allowed Actions

You may:

- Run tests, backtests, validation scripts/notebooks, and metric checks.
- Inspect outputs for leakage, cost sensitivity, parameter stability, split behavior, and failure cases.
- Add or adjust validation checks within scripts/notebooks if they are required to verify the agreed spec.
- Mark the idea as invalid, inconclusive, or provisionally interesting.

You must not:

- Treat a single backtest as proof.
- Tune parameters after seeing results unless Phase 04 allowed it.
- Ignore failed checks.
- Promote the result to paper/live trading.

## Required Output

Return:

```markdown
## Validation Results
- Leakage checks: (specifically verify features do not leak target triple-barrier info, and purging/embargoing was active and correct)
- Primary Model Scorecard Check: (verify win rate 30%-45%, Profit Factor 0.85-1.15, event count 1,000+, market correlation < 0.3)
- Meta-labeler performance: (e.g., test set precision, recall, calibration of probabilities, and performance lift/improvement over the primary strategy alone)
- Bar stability/sensitivity: (e.g., sensitivity of strategy metrics to volume/dollar bar size thresholds; statistical properties like return normality vs time bars)
- Cost/slippage sensitivity:
- Liquidity/capacity checks:
- Train/validation/test behavior:
- Parameter stability:
- Benchmark/baseline comparison:
- Failure case checks:
- Reproducibility:

## Research Verdict
- Verdict: invalid | inconclusive | provisionally interesting
- Evidence:
- What would change the verdict:
- What remains untrusted:

## Phase Closeout
- Phase: 06 Validation
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

Append a dated `AI_JOURNAL.md` entry with validation commands, results, verdict, failures, and remaining untrusted claims.

## Handoff Command

Update `SESSION_HANDOFF.md` with the validation verdict, artifacts to inspect next, known risks, and the exact Phase 07 prompt to paste.

