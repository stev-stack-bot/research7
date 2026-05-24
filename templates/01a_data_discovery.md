# Phase 01A Prompt: Data Discovery

Identify feasible data sources and acquisition paths for the selected research question before formal data audit.

This phase discovers candidate data. It does not certify data quality. Phase 02 must still audit any selected source.

## Read First

Read:

- `SESSION_HANDOFF.md`
- Latest relevant `AI_JOURNAL.md` entries.
- Phase 00A idea supply output, if present.
- Phase 01 research question/spec.
- Existing repo data docs, data loaders, cached samples, configs, and files/notebooks.

## Previous-State Dependency

Begin by summarizing:

- Selected hypothesis.
- Required instruments, universe, timeframe, and frequency.
- Required data fields.
- Existing proposed source candidates.
- Constraints around credentials, paid data, and local availability.

## Allowed Actions

You may:

- Inspect local repo data and loaders.
- Identify public, free-with-key, and paid/vendor data source candidates.
- Compare source coverage, fields, adjustment semantics, latency, licensing, and practical access path.
- Recommend one primary source and one fallback for Phase 02 audit.
- Ask for human approval before any credentialed, paid, or network-dependent acquisition.

You must not:

- Use or request broker credentials.
- Connect to paid or credentialed APIs without explicit human approval.
- Treat source availability as proof of data quality.
- Download large datasets without explicit approval.
- Backtest or implement signal logic.

## Required Output

Return:

```markdown
## Data Requirements
- Instruments/universe:
- Timeframe:
- Bar aggregation type & frequency: standard time candles | volume bars | dollar bars
- Required fields: (specify if tick/trade-level logs containing timestamp, size, and price are needed for volume/dollar bars)
- Optional fields:
- Minimum history:
- Corporate action needs:
- Calendar/timezone needs:

## Source Candidates
| Source | Access Type | Fields Fit | Coverage Fit | Adjustment Semantics | Main Risks | Audit Priority |
| --- | --- | --- | --- | --- | --- | --- |
|  | available locally |  |  |  |  |  |
|  | free public |  |  |  |  |  |
|  | free with API key |  |  |  |  |  |
|  | paid/vendor |  |  |  |  |  |

## Recommendation
- Primary candidate for Phase 02 audit:
- Fallback candidate:
- Sources rejected:
- Human approvals needed:
- Acquisition path:

## Phase Closeout
- Phase: 01A Data Discovery
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

Append a dated `AI_JOURNAL.md` entry with required data fields, source candidates, rejected sources, recommended audit target, approvals needed, and next action.

## Handoff Command

Update `SESSION_HANDOFF.md` with the selected data candidate, fallback source, acquisition path, unresolved approvals, and the exact Phase 02 prompt to paste.

