# AI Journal

This is the append-only memory for the retail quant research harness.

Do not delete or rewrite prior entries unless repairing obvious formatting corruption. Every meaningful AI session must append a dated entry.

## Entry Template

```markdown
## YYYY-MM-DD HH:MM Local - Phase NN: Phase Name

### User Request
- 

### Context Read
- `SESSION_HANDOFF.md`:
- `AI_JOURNAL.md`:
- Repo files/artifacts:

### Actions Taken
- 

### Files Changed
- 

### Commands Or Checks Run
- 

### Decisions Made
- 

### Evidence
- 

### Assumptions
- 

### Failures, Risks, Or Blockers
- 

### Next Action
- 
```

## 2026-05-20 Initial - Phase 00: Harness Creation

### User Request
- Create a repo-local prompt template playbook for research-focused retail quant trading development in IDE assistants.
- Require phase-by-phase prompts, previous-step dependency, repeated journaling, and a handoff file usable across new conversations.

### Context Read
- `SESSION_HANDOFF.md`: not present before harness creation.
- `AI_JOURNAL.md`: not present before harness creation.
- Repo files/artifacts: repo was empty at creation time.

### Actions Taken
- Created the markdown-first harness structure.
- Added phase templates for bootstrap, research question, data audit, signal design, backtest design, implementation, validation, review, and journal/handoff.

### Files Changed
- `PROMPT_PLAYBOOK.md`
- `AI_JOURNAL.md`
- `SESSION_HANDOFF.md`
- `templates/00_session_bootstrap.md`
- `templates/01_research_question.md`
- `templates/02_data_audit.md`
- `templates/03_feature_signal_design.md`
- `templates/04_backtest_design.md`
- `templates/05_implementation.md`
- `templates/06_validation.md`
- `templates/07_review.md`
- `templates/08_journal_handoff.md`

### Commands Or Checks Run
- Repo listing confirmed no existing files before creation.

### Decisions Made
- Defaulted to Python research workflows using pandas/polars, notebooks or scripts, backtesting-style engines, and pytest-style validation.
- Set live trading, paper trading, broker execution, and credential handling out of scope by default.
- Used append-only journaling plus compact mutable session handoff as the state persistence mechanism.

### Evidence
- The initial repo had no visible files.
- The user explicitly requested a research-focused retail quant trading harness with prompts for every phase and durable records.

### Assumptions
- The user wants markdown files committed directly into the repo.
- Future strategy work should start with `templates/00_session_bootstrap.md`.

### Failures, Risks, Or Blockers
- None at creation time.

### Next Action
- Start the first strategy research task by pasting `templates/00_session_bootstrap.md`, then `templates/01_research_question.md`.

## 2026-05-20 21:57 Local - Phase 00: Harness Extension

### User Request
- Add support for the AI to supply or resupply strategy ideas and automatically find the data needed.

### Context Read
- `SESSION_HANDOFF.md`: harness existed with no active research question.
- `AI_JOURNAL.md`: initial harness creation entry existed.
- Repo files/artifacts: reviewed `PROMPT_PLAYBOOK.md`, `templates/01_research_question.md`, and `templates/02_data_audit.md`.

### Actions Taken
- Added a dedicated idea supply/resupply phase.
- Added a dedicated data discovery phase before formal data audit.
- Updated the playbook phase table, usage guidance, guardrails, handoff, and existing templates to route through the new phases when needed.

### Files Changed
- `PROMPT_PLAYBOOK.md`
- `SESSION_HANDOFF.md`
- `AI_JOURNAL.md`
- `templates/00_session_bootstrap.md`
- `templates/01_research_question.md`
- `templates/02_data_audit.md`
- `templates/00a_idea_supply.md`
- `templates/01a_data_discovery.md`

### Commands Or Checks Run
- Read current playbook, handoff, and Phase 01/02 templates.
- Retrieved local timestamp for the journal entry.

### Decisions Made
- Kept idea supply as Phase 00A so it can run when no human idea exists or when an idea is invalidated.
- Kept data discovery as Phase 01A so candidate sources are identified before Phase 02 audits the chosen source.
- Required the AI to rank ideas by researchability and data feasibility rather than novelty or expected profit.

### Evidence
- The previous handoff said no strategy research had started.
- The user explicitly requested AI-supplied ideas and automatic data identification.

### Assumptions
- Data discovery may identify candidate sources, but credentialed, paid, or large-download acquisition still needs explicit human approval.
- Data discovery does not replace formal data audit.

### Failures, Risks, Or Blockers
- Markdown prompts cannot technically force an IDE assistant to comply; compliance depends on pasting and enforcing the templates.

### Next Action
- Start with `templates/00_session_bootstrap.md`, then use `templates/00a_idea_supply.md` if no human-provided idea exists.

## 2026-05-22 14:30 Local - Phase 00: Harness Expansion (Meta-Labeling & Volume/Dollar Bars)

### User Request
- Include training a meta-labeling model in the research harness.
- Add support for volume bars or dollar bars when trades data is available instead of aggregating into standard time candles.

### Context Read
- `SESSION_HANDOFF.md`
- `AI_JOURNAL.md`
- `PROMPT_PLAYBOOK.md`
- `templates/` directory contents

### Actions Taken
- Updated the research guardrails in `PROMPT_PLAYBOOK.md` to explicitly define volume/dollar bars and meta-labeling best practices (e.g. purging/embargoing).
- Integrated volume/dollar bar choices and raw trade/tick data requirements into `templates/01_research_question.md`, `templates/01a_data_discovery.md`, and `templates/02_data_audit.md`.
- Expanded `templates/03_feature_signal_design.md` with sections for Bar Construction details and Meta-Labeling Model specification (including Triple Barrier target bounds, secondary features, and purging/embargo policy).
- Updated `templates/04_backtest_design.md` to include volume/dollar bar aggregation details, meta-labeling position sizing logic, and baseline comparisons (primary strategy alone vs primary + meta-labeling).
- Updated `templates/05_implementation.md` to require implementation summaries and tests for bar aggregation, meta-labeling training, and purging/embargo checks.
- Modified `templates/06_validation.md` to include specific validations for meta-labeler performance metrics, bar parameter stability, and leakage checks under purging/embargoing constraints.

### Files Changed
- `PROMPT_PLAYBOOK.md`
- `templates/01_research_question.md`
- `templates/01a_data_discovery.md`
- `templates/02_data_audit.md`
- `templates/03_feature_signal_design.md`
- `templates/04_backtest_design.md`
- `templates/05_implementation.md`
- `templates/06_validation.md`

### Commands Or Checks Run
- Listed project directory and templates directory.
- Checked lines and content of all target template files before making updates.

### Decisions Made
- Embedded volume/dollar bars and meta-labeling directly into the existing research template progression rather than creating new independent phases. This maintains simplicity while adding capability.
- Explicitly emphasized purging and embargoing in the design, implementation, and validation templates to protect against the high risk of lookahead/overlap leakage associated with meta-labeling targets.

### Evidence
- The updated templates now contain clear placeholders and guidance for alternative bars and meta-labeling across the research lifecycle.

### Assumptions
- Trade-level (tick/trades) data is available to the researcher when volume/dollar bars are chosen; otherwise, standard time candles remain the default.
- Meta-labeling models are optional and designed to complement a primary signal rather than serve as a standalone strategy.

### Failures, Risks, Or Blockers
- None. The prompt harness structures are successfully expanded.

### Next Action
- Reconstruct session state using `templates/00_session_bootstrap.md`, and begin Phase 00A or Phase 01 for the first trading strategy.

## 2026-05-22 14:38 Local - Phase 00: Harness Enforcers (Notebook-Only Stack)

### User Request
- All code must be written in Jupyter Notebooks.

### Context Read
- `SESSION_HANDOFF.md`
- `AI_JOURNAL.md`
- `PROMPT_PLAYBOOK.md`
- `templates/` directory contents

### Actions Taken
- Modified `PROMPT_PLAYBOOK.md` to restrict research artifacts to Jupyter Notebooks (`.ipynb` files) and replace pytest/script checks with notebook-based checks and cells.
- Updated `SESSION_HANDOFF.md` latest verified facts to specify Jupyter Notebooks exclusively.
- Updated `templates/03_feature_signal_design.md` and `templates/04_backtest_design.md` to replace file/module references with notebooks.
- Updated `templates/05_implementation.md` and `templates/06_validation.md` to restrict code creation, execution, and validation to Jupyter Notebooks (`.ipynb`), explicitly banning standard Python scripts (`.py`).

### Files Changed
- `PROMPT_PLAYBOOK.md`
- `SESSION_HANDOFF.md`
- `templates/03_feature_signal_design.md`
- `templates/04_backtest_design.md`
- `templates/05_implementation.md`
- `templates/06_validation.md`

### Commands Or Checks Run
- Ran grep search for remaining references to "scripts" and "modules".
- Validated changed files.

### Decisions Made
- Replaced standard file/module terminology with notebook/cell terminology in both the playbook and templates to prevent the assistant from falling back on creating traditional scripts.

### Evidence
- The templates now strictly prohibit python scripts (.py) and mandate notebook-based research, implementation, and validation workflows.

### Assumptions
- Notebooks are execution-safe and are the preferred medium for interactive research and validation verification.

### Failures, Risks, Or Blockers
- None.

### Next Action
- Reconstruct session state using `templates/00_session_bootstrap.md`, and begin Phase 00A or Phase 01 for the first trading strategy.

## 2026-05-23 13:38 Local - Phase 00: Harness Revision (Remove Notebook Exclusivity & Add Lopez de Prado Scorecard)

### User Request
- Remove notebook requirements, ipynb is not needed.
- Integrate the Lopez de Prado scorecard/checklist summary to determine if a primary model is ready for meta-labeling.

### Context Read
- `SESSION_HANDOFF.md`
- `AI_JOURNAL.md`
- `PROMPT_PLAYBOOK.md`
- `templates/` directory contents

### Actions Taken
- Modified `PROMPT_PLAYBOOK.md` to remove exclusive Jupyter notebook requirements and explicitly support standard Python scripts (`.py`).
- Integrated the Lopez de Prado scorecard (Win Rate, Profit Factor, Event Count, Market Correlation) into the meta-labeling section of `PROMPT_PLAYBOOK.md`.
- Updated `SESSION_HANDOFF.md` to remove notebook exclusivity.
- Updated templates `00_session_bootstrap.md`, `01_research_question.md`, `01a_data_discovery.md`, `02_data_audit.md`, `03_feature_signal_design.md`, `04_backtest_design.md`, `05_implementation.md`, and `06_validation.md` to replace "Jupyter Notebooks exclusively" language with standard scripts or notebooks, and added checks/placeholders for the Lopez de Prado scorecard.

### Files Changed
- `PROMPT_PLAYBOOK.md`
- `SESSION_HANDOFF.md`
- `templates/00_session_bootstrap.md`
- `templates/01_research_question.md`
- `templates/01a_data_discovery.md`
- `templates/02_data_audit.md`
- `templates/03_feature_signal_design.md`
- `templates/04_backtest_design.md`
- `templates/05_implementation.md`
- `templates/06_validation.md`
- `AI_JOURNAL.md` (this file)

### Commands Or Checks Run
- Grepped for `notebook` and `.ipynb` to locate all occurrences.
- Validated modified templates to ensure they align with the new script/notebook flexibility.

### Decisions Made
- Allowed both `.py` scripts and `.ipynb` notebooks for implementation, backtesting, and validation.
- Embedded the Lopez de Prado scorecard check directly into Phase 03 (Signal Design), Phase 04 (Backtest Design), and Phase 06 (Validation) templates to enforce evaluating the primary model against these quantitative criteria before building a meta-labeler.

### Evidence
- Grep search confirms there are no longer references to notebook exclusivity or script bans.
- The templates now prompt the user/AI to check the primary model's PF (0.85-1.15), Win Rate (30%-45%), Event Count (1,000+), and Market Correlation (< 0.3).

### Assumptions
- Researchers will choose between scripts and notebooks depending on the complexity and interactive nature of the research step.
- The scorecard criteria will serve as a hard check to freeze primary model logic and prevent overfitting in the meta-labeler.

### Failures, Risks, Or Blockers
- None.

### Next Action
- Reconstruct session state using `templates/00_session_bootstrap.md` and initiate research using the updated guidelines.


