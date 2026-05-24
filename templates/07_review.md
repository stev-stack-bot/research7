# Phase 07 Prompt: Review

Critique the completed research like a skeptical reviewer. Focus on bugs, invalid assumptions, overfitting, weak evidence, and missing tests.

## Read First

Read:

- `SESSION_HANDOFF.md`
- Latest relevant `AI_JOURNAL.md` entries.
- Phase 01 through Phase 06 specs, code, tests, validation outputs, and artifacts.

## Previous-State Dependency

Begin by summarizing:

- Research question.
- Implementation status.
- Validation verdict.
- Known risks and remaining untrusted claims.

## Allowed Actions

You may:

- Review code, specs, tests, metrics, plots, and logs.
- Identify defects, invalid assumptions, missing controls, and weak evidence.
- Recommend follow-up experiments or termination.
- Run focused read-only or validation checks if needed.

You must not:

- Rewrite the strategy to improve results.
- Downplay failed validation.
- Convert research into trading advice.
- Move toward paper/live trading.

## Required Output

Return findings first, ordered by severity:

```markdown
## Review Findings
- Severity:
  - Issue:
  - Evidence:
  - Impact:
  - Required fix or follow-up:

## Open Questions
- 

## Research Disposition
- Disposition: stop | revise | run more validation | archive as provisionally interesting
- Rationale:

## Phase Closeout
- Phase: 07 Review
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

Append a dated `AI_JOURNAL.md` entry with review findings, disposition, unresolved issues, and recommended next action.

## Handoff Command

Update `SESSION_HANDOFF.md` with the review disposition, unresolved issues, and the exact Phase 08 prompt to paste.

