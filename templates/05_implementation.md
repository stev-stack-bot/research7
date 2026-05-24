# Phase 05 Prompt: Implementation

Implement only the agreed research spec. Keep changes scoped and observable.

## Read First

Read:

- `SESSION_HANDOFF.md`
- Latest relevant `AI_JOURNAL.md` entries.
- Phase 01 through Phase 04 specs.
- Existing code, tests, configs, scripts/notebooks, and data docs relevant to the implementation contract.

## Previous-State Dependency

Begin by summarizing:

- Hypothesis.
- Data audit decision.
- Signal spec.
- Backtest design.
- Implementation contract.
- Tests/checks required by Phase 04.

If any required spec is missing or contradictory, stop and ask for the missing decision instead of coding.

## Allowed Actions

You may:

- Edit research code, configs, scripts/notebooks, and markdown artifacts needed for the agreed spec.
- Add focused tests or validation checks within scripts/notebooks.
- Run local checks.
- Record all touched files and commands.

You must not:

- Change the research question without journaling the change.
- Add live trading, broker execution, or credential handling.
- Optimize strategy parameters unless Phase 04 explicitly defined an allowed parameter policy.
- Hide failing checks.
- Rewrite unrelated code.

## Required Output

Return:

```markdown
## Implementation Summary
- Scope implemented:
- Files changed:
- Research behavior added: (e.g., volume/dollar bar construction, primary model/rules, meta-labeler, triple barrier labeling, purging/embargo logic)
- Tests/checks added: (e.g., bar volume/dollar conservation, purging/embargo index isolation, non-leaky feature checks, unit tests)
- Artifacts generated:
 
## Deviations From Spec
- Deviations:
- Reason:
- Impact:
 
## Verification
- Commands/checks run:
- Results: (e.g. pytest output, leakage test results)
- Known failures:
- Validation still required:

## Phase Closeout
- Phase: 05 Implementation
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

Append a dated `AI_JOURNAL.md` entry with touched files, behavior implemented, commands/checks run, deviations, failures, and next validation actions.

## Handoff Command

Update `SESSION_HANDOFF.md` with current implementation status, files to inspect next, known failures, and the exact Phase 06 prompt to paste.

