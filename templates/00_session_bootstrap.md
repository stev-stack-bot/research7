# Phase 00 Prompt: Session Bootstrap

You are working inside a research-only retail quant trading repo. Before doing any research, coding, analysis, or recommendations, reconstruct the current project state.

## Read First

Read these files before responding:

- `SESSION_HANDOFF.md`
- `AI_JOURNAL.md`
- `PROMPT_PLAYBOOK.md`
- Relevant repo files, configs, tests, scripts/notebooks, experiment outputs, and data docs mentioned in the handoff.

If any required file is missing, say exactly which file is missing and continue with the available context.

## Previous-State Dependency

Start by summarizing:

- Current phase from `SESSION_HANDOFF.md`.
- Current research question, if any.
- Latest verified facts.
- Active assumptions.
- Known risks.
- Next exact prompt from the handoff.

Do not rely on memory from prior chat unless it is also recorded in repo files.

## Allowed Actions

You may:

- Read files.
- Inspect repo structure.
- Summarize state.
- Identify missing artifacts.
- Recommend the next phase.

You must not:

- Place trades or connect to a broker.
- Read, write, or request credentials.
- Change live or paper trading behavior.
- Start implementation before the research phase is known.
- Invent prior decisions not present in the handoff or journal.

## Required Output

Return:

```markdown
## Bootstrap Summary
- Current phase:
- Current research question:
- Latest verified facts:
- Active assumptions:
- Known risks:
- Missing files or artifacts:
- Recommended next phase:
- Whether AI idea supply is needed:

## Context Map
- Files read:
- Files that appear important but were not read:
- Artifacts needed next:

## Phase Closeout
- Phase: 00 Session Bootstrap
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

If this bootstrap materially changes understanding of project state, append a dated entry to `AI_JOURNAL.md`. If it only reads state and makes no decisions, journal update is optional but explain why.

## Handoff Command

If the next phase or known risks changed, update `SESSION_HANDOFF.md`. Otherwise, leave it unchanged and say why.
