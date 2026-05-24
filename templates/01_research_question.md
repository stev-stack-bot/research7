# Phase 01 Prompt: Research Question

Convert a trading idea into a falsifiable research question. Do not code yet.

## Read First

Read:

- `SESSION_HANDOFF.md`
- Latest relevant entries in `AI_JOURNAL.md`
- `PROMPT_PLAYBOOK.md`
- Any existing research notes, strategy specs, files/notebooks, or data docs related to the idea.
- `templates/00a_idea_supply.md` output if the idea was AI-supplied.

## Previous-State Dependency

Begin by summarizing what Phase 00 established:

- Current project state.
- Whether a research idea already exists.
- Any constraints, assumptions, or risks from the handoff.

If the user supplied a new idea, reconcile it with the handoff and state whether it replaces or extends the current research question.

If the idea was AI-supplied, restate why it was selected from the candidate list and what quick-rejection criteria were proposed.

## Allowed Actions

You may:

- Clarify the research idea.
- Define hypothesis, universe, timeframe, data needs, benchmark, and invalidation criteria.
- Identify required data and validation gates.
- Ask only high-impact questions that cannot be answered from repo context.

You must not:

- Implement code.
- Optimize parameters.
- Backtest.
- Treat the idea as profitable before evidence exists.
- Move toward live or paper trading.

## Required Output

Return:

```markdown
## Research Question Spec
- Working title:
- Hypothesis:
- Market/universe:
- Instrument constraints:
- Timeframe:
- Bar type & frequency: standard time candles | volume bars | dollar bars (include threshold/size details if known)
- Meta-labeling model proposed: yes | no (if yes, proposed model type and target definition)
- Data source candidates:
- Data fields required: (specify if tick/trade-level data is required for volume/dollar bars)
- Data feasibility: known | unknown | needs Phase 01A discovery
- Benchmark:
- Baseline comparison:
- Invalidation criteria:
- Minimum viable test:

## Research Risks
- Leakage risks:
- Bias risks:
- Cost/slippage risks:
- Liquidity/capacity risks:
- Overfitting risks:
- Data availability risks:

## Decisions Needed
- Human decisions:
- Assumptions if unanswered:

## Phase Closeout
- Phase: 01 Research Question
- Status: complete | blocked | needs human decision
- Files inspected:
- Files changed:
- Commands/checks run:
- Key evidence:
- Assumptions:
- Failures or risks:
- Journal updated: yes | no, why
- Handoff updated: yes | no, why
- Next recommended phase: 01A Data Discovery if data feasibility is unknown; otherwise 02 Data Audit
- Copy-paste next prompt:
```

## Journal Command

Append a dated `AI_JOURNAL.md` entry recording the final hypothesis, assumptions, invalidation criteria, and next action.

## Handoff Command

Update `SESSION_HANDOFF.md` with the current research question, active assumptions, files to read next, and the exact Phase 01A or Phase 02 prompt to paste.
