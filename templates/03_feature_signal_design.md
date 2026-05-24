# Phase 03 Prompt: Feature And Signal Design

Specify the signal logic and leakage controls before implementation. Do not backtest yet.

## Read First

Read:

- `SESSION_HANDOFF.md`
- Latest relevant `AI_JOURNAL.md` entries.
- Phase 01 research question/spec.
- Phase 02 data audit result.
- Existing feature, indicator, strategy, or signal files/notebooks if present.

## Previous-State Dependency

Begin by summarizing:

- Current hypothesis.
- Data fitness decision.
- Data limitations that constrain the signal.
- Invalidation criteria.

## Allowed Actions

You may:

- Specify features, transformations, lags, entry/exit conditions, and signal timing.
- Define expected economic rationale.
- Define leakage controls.
- Identify parameters and reasonable fixed defaults for the first test.
- Identify what code modules would likely change later.

You must not:

- Implement code.
- Tune parameters against returns.
- Backtest.
- Use future bars, close prices, or corporate action fields in ways unavailable at decision time.
- Change the hypothesis to fit the data without recording the change.

## Required Output

Return:

```markdown
## Signal Specification
- Signal name:
- Bar Construction: (detail standard time candles vs volume/dollar bars; include static/dynamic thresholds, aggregation logic, block trade rules)
- Economic rationale:
- Inputs:
- Transformations:
- Lag rules:
- Entry rule: (primary model/rule side decision)
- Exit rule: (primary exit rule)
- Position direction:
- Position sizing input:
- Parameters for first test:
- Forbidden future information:

## Meta-Labeling Model Specification (Optional)
- Meta-labeled primary signal: (the entry rule being evaluated for execution sizing)
- Primary Model Scorecard Readiness: (verify/estimate win rate 30%-45%, Profit Factor 0.85-1.15, event count 1,000+, market correlation < 0.3 before training the meta-labeler)
- Secondary label definition: (e.g. Triple Barrier Method boundaries: profit take (pt) multiplier, stop loss (sl) multiplier, vertical barrier time-to-live)
- Secondary features: (non-leaky features predicting primary signal success: e.g., regime, volatility, bar time-to-fill)
- Model selection: (e.g., Logistic Regression, Random Forest, probability threshold)
- Purging and Embargo policy: (specifically how training labels overlapping validation/test boundaries are handled to avoid data leakage)

## Leakage Controls
- Decision timestamp:
- Execution timestamp:
- Feature availability:
- Train/validation/test separation:
- Known unsafe shortcuts:

## Implementation Notes For Later
- Likely files/notebooks:
- Tests/checks needed:
- Open questions:

## Phase Closeout
- Phase: 03 Feature And Signal Design
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

Append a dated `AI_JOURNAL.md` entry with the final signal spec, lag rules, leakage controls, and open questions.

## Handoff Command

Update `SESSION_HANDOFF.md` with the signal spec summary, active assumptions, artifacts to read next, and the exact Phase 04 prompt to paste.

