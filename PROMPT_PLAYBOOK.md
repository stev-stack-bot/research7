# Retail Quant Research Prompt Harness Playbook

This playbook is a repo-local prompt harness for research-focused retail quant trading development in IDE assistants such as VS Code, Cursor, Antigravity, Codex, and Claude Code.

Its job is to make the AI work like a controlled research assistant, not a stateless chatbot. Every session must ingest prior state, work inside explicit constraints, verify claims, journal what happened, and leave a usable handoff for the next conversation.

The harness is research-only by default. It must not place trades, connect to broker execution, handle credentials, or change live/paper trading behavior unless a future human instruction explicitly replaces this rule.

## Core Harness Contract

Every AI session must follow this contract before doing research or coding:

1. Read `SESSION_HANDOFF.md`.
2. Read the latest relevant entries in `AI_JOURNAL.md`.
3. Inspect relevant repo files, configs, tests, notebooks, experiment outputs, and data docs before making claims.
4. State what phase it is in and summarize what it believes happened previously.
5. Work only inside the current phase's allowed actions.
6. Record touched files, commands/checks run, findings, assumptions, failures, and next actions.
7. Append a dated journal entry to `AI_JOURNAL.md`.
8. Update `SESSION_HANDOFF.md` before ending a meaningful session.

This structure follows harness-engineering ideas: context ingress, constraints, verification gates, state persistence, observability, failure attribution, and intervention records.

## Repo Files

- `PROMPT_PLAYBOOK.md`: this guide and phase index.
- `AI_JOURNAL.md`: append-only project memory.
- `SESSION_HANDOFF.md`: compact current state for the next chat.
- `templates/`: copy-paste prompt templates for each phase.

## Phase Order

Use these phases in order unless the handoff says a phase is already complete or the user explicitly jumps to a later phase.

| Phase | Template | Purpose |
| --- | --- | --- |
| 00 | `templates/00_session_bootstrap.md` | Reconstruct current project state before acting. |
| 00A | `templates/00a_idea_supply.md` | Let the AI generate or resupply candidate research ideas under explicit constraints. |
| 01 | `templates/01_research_question.md` | Convert an idea into a falsifiable trading hypothesis. |
| 01A | `templates/01a_data_discovery.md` | Let the AI identify feasible data sources and acquisition paths for the selected idea. |
| 02 | `templates/02_data_audit.md` | Validate data provenance, timing, cleanliness, and bias risks. |
| 03 | `templates/03_feature_signal_design.md` | Specify signal logic and leakage controls. |
| 04 | `templates/04_backtest_design.md` | Define execution model, costs, sizing, metrics, and benchmarks. |
| 05 | `templates/05_implementation.md` | Implement only the agreed research spec. |
| 06 | `templates/06_validation.md` | Run leakage, cost, stability, split, and failure checks. |
| 07 | `templates/07_review.md` | Critique the result and identify what would disprove it. |
| 08 | `templates/08_journal_handoff.md` | Append final journal record and refresh the handoff. |

## How To Use In An IDE Assistant

Start every new chat by pasting `templates/00_session_bootstrap.md`. After that, paste the template for the next unfinished phase.

If the assistant starts coding before reading the handoff and journal, stop it and paste the bootstrap template again.

If you do not already have a strategy idea, paste `templates/00a_idea_supply.md` after bootstrap. If an idea exists but data feasibility is unclear, paste `templates/01a_data_discovery.md` after Phase 01 and before Phase 02.

If the assistant produces a result without updating `AI_JOURNAL.md` and `SESSION_HANDOFF.md`, paste `templates/08_journal_handoff.md` before ending the session.

## Research-Only Quant Guardrails

The default stack is Python research:

- Data work: pandas or polars.
- Research artifacts: Standard Python scripts (`.py` files), Jupyter Notebooks (`.ipynb` files), markdown reports, parquet/csv/parquet outputs. Research, backtest, validation, and implementation code can be written in standard scripts or notebooks.
- Backtesting: vectorbt, backtesting.py, backtrader, or a programmatic/notebook-integrated engine.
- Validation: script/notebook-based checks, programmatic test verification, and saved metrics.

Every strategy research task must address:

- Lookahead leakage.
- Survivorship bias.
- Data snooping and overfitting.
- Transaction costs and slippage.
- Liquidity and capacity assumptions.
- Timezone, market calendar, and session boundaries.
- Corporate actions and adjusted/unadjusted prices.
- Benchmark and baseline comparison.
- In-sample, validation, and out-of-sample split.
- Parameter stability and sensitivity.
- **Volume/Dollar Bars**: When tick or trades-level data is available, process it into volume bars (fixed quantity traded) or dollar bars (fixed dollar value traded) instead of time-standard candles. Document the threshold selection, distribution properties, and handling of huge block/split trades.
- **Meta-Labeling**: Optionally train a secondary machine learning model (meta-labeler) to predict whether to take a primary model/rule signal (binary outcome: take or pass) and/or to adjust position size.
  - **Primary Model Lopez de Prado Scorecard**: Before training the meta-labeler, evaluate the primary model to ensure it is ready for meta-labeling (strictly an **opportunity identification** radar):
    1. **Profit Factor Target Zone (0.85 to 1.15)**: The primary model should be marginally unprofitable to slightly profitable. If PF < 0.7, it's pure noise (scrap it). If PF > 1.5, it's ready to trade on its own (no meta-labeler needed). The break-even zone is where the meta-labeler thrives by filtering false positives.
    2. **Payout Asymmetry (High Recall, 30% - 40% Win Rate)**: When right, it makes significantly more than it loses (e.g., 3:1 or 4:1 Reward-to-Risk ratio via Triple Barrier profit/stop widths). The profit barrier is hit less frequently than the stop barrier, but is much wider.
    3. **High Event Frequency (1,000+ instances)**: The primary model must generate at least 1,000+ events/trades in the training set to prevent the meta-model from overfitting. Lower the primary signal threshold if needed to increase frequency.
    4. **Orthogonality to Market (Correlation < 0.3)**: Equity curve returns should flatline or generate returns independent of the broader market price curve (correlation near 0).
    - **Scorecard Checklist Summary**:
      - *Win Rate*: 30% – 45% (leaves room for precision improvement)
      - *Profit Factor*: ~0.85 – 1.15 (proves it isn't bleeding out from random noise)
      - *Event Count*: 1,000+ instances (required to train ML without overfitting)
      - *Market Correlation*: < 0.3 (proves edge, not market beta)
    - If the primary model meets these metrics, freeze its logic, extract features at event timestamps, label them 1 (profitable) / 0 (unprofitable), and train the meta-labeler.
  - Define labels using the Triple Barrier Method (profit target, stop-loss, and time/bar expiry).
  - Prevent overlap-induced lookahead leakage using data purging (removing training labels that overlap with test set times) and embargoing (removing training data immediately following the test set due to auto-correlation).
  - Use features calculated strictly before the decision time.

Promising results are untrusted until validation gates pass.

## AI Idea Supply And Data Discovery

The assistant may supply strategy ideas when the user asks for ideas, when the handoff says no current research question exists, or when a prior idea is rejected, invalidated, blocked by data, or archived.

AI-supplied ideas must be ranked by researchability, not excitement. Each idea must include:

- Market anomaly or behavioral rationale.
- Required instruments and universe.
- Required data fields.
- Feasible retail-accessible data source candidates.
- Known bias and leakage risks.
- Minimum viable test.
- Reason to reject quickly.

The assistant may discover data sources and acquisition paths, but it must distinguish:

- `Available locally`: data already present in the repo.
- `Free public`: data that can likely be acquired without credentials.
- `Free with API key`: data requiring explicit human-approved credentials.
- `Paid/vendor`: data requiring subscription or license review.
- `Not feasible`: data that is unavailable, unsafe, too expensive, or unsuitable for retail research.

Data discovery is not data audit. A source is only a candidate until Phase 02 validates provenance, timing, adjustments, missingness, and bias risks.

## Required Vocabulary

The assistant must separate these categories:

- `Hypothesis`: a falsifiable claim about market behavior.
- `Evidence`: observed data, metrics, tests, plots, or code facts.
- `Implementation detail`: how the repo expresses the research.
- `Assumption`: an unproven input or simplification.
- `Open question`: a decision or missing fact that affects conclusions.
- `Failure`: a bug, invalid result, blocked check, or disproven claim.

## Standard Output Block

Every phase response should end with this block:

```markdown
## Phase Closeout
- Phase:
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

## Journal Rules

`AI_JOURNAL.md` is append-only. Do not rewrite prior entries except to fix obvious formatting corruption.

Each entry must include:

- Date and local time.
- Phase.
- User request.
- Context read.
- Actions taken.
- Files changed.
- Checks run and results.
- Decisions made.
- Evidence found.
- Assumptions.
- Failures or blockers.
- Next action.

## Handoff Rules

`SESSION_HANDOFF.md` is mutable and should stay compact. It must describe the current state of the project, not the whole history.

Every handoff must include:

- Current phase.
- Current research question.
- Latest verified facts.
- Active assumptions.
- Files/artifacts to read next.
- Validation status.
- Known risks.
- Next exact prompt to paste.

## Safety Boundary

The assistant must refuse or pause before:

- Placing trades.
- Sending broker orders.
- Reading or writing broker credentials.
- Disabling risk checks.
- Optimizing solely for backtest performance without validation.
- Treating backtest profit as investment advice.
- Moving from research to paper/live trading without a new explicit human instruction.

## Dry-Run Scenario

Use this sample idea to test the harness:

> Research whether SPY mean-reverts after large gap-down opens.

A good dry run should produce:

- A falsifiable hypothesis.
- A data audit plan.
- Explicit leakage and cost controls.
- A backtest design before implementation.
- A validation checklist.
- A journal entry.
- A handoff that lets a fresh chat continue without prior conversation context.
