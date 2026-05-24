# Phase 08 Prompt: Journal And Handoff

Close the session by making project state durable. This phase is required before ending any meaningful research or implementation session.

## Read First

Read:

- `SESSION_HANDOFF.md`
- Latest relevant `AI_JOURNAL.md` entries.
- All phase outputs produced in this session.
- Any code, tests, reports, logs, plots, or artifacts changed or generated in this session.

## Previous-State Dependency

Begin by summarizing:

- What phase was active before this closeout.
- What changed in this session.
- What evidence was produced.
- What remains unresolved.

## Allowed Actions

You may:

- Append to `AI_JOURNAL.md`.
- Update `SESSION_HANDOFF.md`.
- Summarize artifacts and next actions.
- Identify the next exact prompt for a fresh chat.

You must not:

- Modify strategy logic except to repair journal/handoff references.
- Delete prior journal history.
- Claim validation passed unless the evidence is recorded.
- Move toward paper/live trading.

## Required Output

Return:

```markdown
## Durable State Update
- Journal entry appended:
- Handoff updated:
- Current phase:
- Current research question:
- Latest verified facts:
- Active assumptions:
- Validation status:
- Known risks:
- Next exact prompt:

## Fresh-Chat Reconstruction Test
- Could a fresh AI continue from `SESSION_HANDOFF.md` and `AI_JOURNAL.md` alone: yes | no
- Missing context:
- Fix applied or needed:

## Phase Closeout
- Phase: 08 Journal And Handoff
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

Append a dated final session entry to `AI_JOURNAL.md`. Include the user request, context read, actions taken, files changed, checks run, decisions made, evidence, assumptions, failures/blockers, and next action.

## Handoff Command

Update `SESSION_HANDOFF.md` so a fresh chat can continue without reading the prior conversation. Keep it compact and current.

