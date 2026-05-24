# Phase 00A Prompt: AI Idea Supply And Resupply

Generate candidate retail quant research ideas when no active idea exists, when the user asks for ideas, or when a prior idea is invalidated, blocked, or archived.

The goal is not to be exciting. The goal is to supply researchable, falsifiable, retail-accessible ideas that can be rejected quickly if the evidence is weak.

## Read First

Read:

- `SESSION_HANDOFF.md`
- Latest relevant entries in `AI_JOURNAL.md`
- `PROMPT_PLAYBOOK.md`
- Existing research notes, strategy specs, validation results, rejected ideas, and available local data docs.

## Previous-State Dependency

Begin by summarizing:

- Current project state.
- Whether there is an active research question.
- Ideas already tested, rejected, blocked, or archived.
- Available local data or known data constraints.
- User constraints from the handoff.

If an active research question already exists, explain whether idea resupply is appropriate. Do not replace an active idea unless the user asked to resupply or the handoff says the idea is blocked, invalidated, or archived.

## Allowed Actions

You may:

- Propose candidate ideas from market structure, behavioral effects, calendar effects, cross-sectional effects, volatility effects, liquidity effects, and simple statistical anomalies.
- Rank ideas by researchability, data feasibility, falsifiability, and retail practicality.
- Identify required data fields and likely source candidates.
- Recommend one idea for Phase 01.

You must not:

- Claim an idea is profitable.
- Backtest.
- Implement code.
- Recommend live or paper trading.
- Require paid, credentialed, or hard-to-license data unless clearly labeled as optional.
- Hide obvious reasons an idea may fail.

## Required Output

Return:

```markdown
## Idea Supply Summary
- Reason idea supply/resupply is needed:
- Existing ideas considered:
- Available local data constraints:
- User constraints:

## Candidate Ideas
| Rank | Idea | Hypothesis Sketch | Required Data | Data Feasibility | Main Risk | Quick-Rejection Test |
| --- | --- | --- | --- | --- | --- | --- |
| 1 |  |  |  |  |  |  |
| 2 |  |  |  |  |  |  |
| 3 |  |  |  |  |  |  |

## Recommended Idea For Phase 01
- Working title:
- Why this one:
- Required data fields:
- Candidate data sources:
- Fastest falsification path:
- Reasons to reject early:

## Phase Closeout
- Phase: 00A Idea Supply And Resupply
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

Append a dated `AI_JOURNAL.md` entry recording the candidate ideas, ranking rationale, rejected/blocked ideas considered, recommended idea, assumptions, and next action.

## Handoff Command

Update `SESSION_HANDOFF.md` with the recommended idea, candidate alternatives, required data fields, active assumptions, and the exact Phase 01 prompt to paste.

