# Session Handoff

## Current Phase
- Phase 00: Harness created.

## Current Research Question
- None yet. The harness is ready for the first strategy idea.

## Latest Verified Facts
- This repo contains a markdown-first prompt harness for research-focused retail quant trading development.
- The default stack is Python research with pandas/polars, scripts (.py) or Jupyter Notebooks (.ipynb), programmatic or notebook-integrated engines, and script/notebook-based validation.
- Live trading, paper trading, broker execution, and credential handling are out of scope unless a future human instruction explicitly changes that boundary.
- The harness supports AI-supplied idea generation/resupply and AI-assisted data-source discovery before formal data audit.
- The harness now incorporates explicit templates and guardrails for constructing volume/dollar bars from trade-level data, designing and implementing meta-labeling models, and validating them with purging and embargoing leakage controls.

## Active Assumptions
- Every new AI chat should begin by reading this file, then `AI_JOURNAL.md`, then the relevant template for the next phase.
- Strategy research must treat promising backtest results as untrusted until validation gates pass.
- The assistant must append journal entries and update this handoff after meaningful work.

## Files And Artifacts To Read Next
- `PROMPT_PLAYBOOK.md`
- `AI_JOURNAL.md`
- `templates/00_session_bootstrap.md`
- `templates/00a_idea_supply.md`
- `templates/01_research_question.md`
- `templates/01a_data_discovery.md`

## Validation Status
- Harness structure created.
- No strategy research has been started.
- No dry-run strategy has been performed yet.

## Known Risks
- A future assistant may skip the journal/handoff update unless the templates are pasted explicitly.
- The harness is markdown-enforced, not programmatically enforced.

## Next Exact Prompt To Paste

```markdown
Use `templates/00_session_bootstrap.md` and follow it exactly. After reconstructing the project state, if no research idea is supplied, use `templates/00a_idea_supply.md` to propose candidate ideas before Phase 01.
```
