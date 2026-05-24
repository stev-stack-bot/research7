# Phase 02 Prompt: Data Audit

Audit the proposed data before signal design or backtesting. Do not implement strategy logic yet.

## Read First

Read:

- `SESSION_HANDOFF.md`
- Latest relevant `AI_JOURNAL.md` entries.
- Phase 01 research question/spec.
- Phase 01A data discovery result, if present.
- Existing data docs, loaders, schemas, files/notebooks, cached data samples, and config files.

## Previous-State Dependency

Begin by summarizing:

- The current hypothesis.
- Required market/universe/timeframe/frequency.
- Data sources proposed in Phase 01.
- Data source candidates discovered in Phase 01A, if present.
- Invalidation criteria and minimum viable test.

## Allowed Actions

You may:

- Inspect data files, schemas, loaders, and samples.
- Run non-mutating data checks or create temporary scratch outputs if needed.
- Identify provenance, coverage, missingness, timestamp conventions, adjustment rules, and vendor limitations.
- Recommend whether data is fit for the minimum viable test.

You must not:

- Design the alpha signal before data constraints are known.
- Backtest the strategy.
- Fill missing data silently.
- Ignore adjusted/unadjusted price semantics.
- Connect to paid or credentialed APIs without explicit human approval.

## Required Output

Return:

```markdown
## Data Audit
- Data sources inspected:
- Candidate sources rejected before audit:
- Coverage:
- Timestamp/timezone/session handling: (e.g. tick timestamp precision, millisecond resolution)
- Corporate action handling:
- Adjusted vs unadjusted fields:
- Trade/tick-level checks: (if constructing volume/dollar bars, address tick gaps, bad prints, block trades, split orders, and volume field cleanliness)
- Missing data:
- Duplicates/outliers:
- Survivorship risk:
- Lookahead risk:
- Vendor limitations:
- Data license/access constraints:

## Fitness Decision
- Fit for minimum viable test: yes | no | conditional
- Required fixes before signal design:
- Acceptable assumptions:
- Disqualifying issues:

## Phase Closeout
- Phase: 02 Data Audit
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

Append a dated `AI_JOURNAL.md` entry with data sources inspected, evidence, data risks, and the data fitness decision.

## Handoff Command

Update `SESSION_HANDOFF.md` with the data audit result, unresolved data risks, artifacts to read next, and the exact Phase 03 prompt to paste.
