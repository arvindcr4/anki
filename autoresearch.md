# Autoresearch: LLM-era intake UX for Anki Add Cards

## Objective
Improve Anki's Add Cards experience for the LLM era by making source capture more discoverable, lower-friction, and better organized. The target workflow is: a learner opens Add Cards, immediately sees how to drop a file or URL, sees where future LLM setup belongs, and can keep imported material neatly organized without hunting through menus.

## Metrics
- **Primary**: `llm_intake_score` (unitless, higher is better)
- **Secondary**: `syntax_ok` (Python compile check), `research_doc_ready` (design guidance captured), `organization_support` (visible organization affordances)

## How to Run
`./autoresearch.sh`

The script performs a fast Python syntax check on the in-scope Python files and then scores the current implementation against the target UX:
- discoverable drop zone / quick intake surface
- explicit file + URL capture entry points
- visible LLM setup affordance
- organization affordances for deck / note type / tags
- source-aware tagging / guidance
- design research captured in repo docs

## Files in Scope
- `qt/aqt/addcards.py` — Add Cards window orchestration; best place for intake banner, buttons, drop zone, and organization helpers.
- `qt/aqt/forms/addcards.ui` — layout shell for Add Cards; may need spacing or placement adjustments.
- `qt/aqt/editor.py` — existing paste/URL/file insertion logic that can be reused by new quick-intake actions.
- `docs/llm-intake-ux.md` — research-backed product notes for a simpler LLM-era learning flow.
- `autoresearch.md` / `autoresearch.sh` — experiment context and benchmark harness.

## Off Limits
- Scheduling / FSRS logic
- Rust backend / storage layer
- Reviewer flow outside what is needed to support the Add Cards prototype
- New runtime dependencies

## Constraints
- Reuse existing editor insertion logic instead of inventing a parallel media pipeline.
- Keep changes scoped to the Add Cards experience.
- Prefer discoverability and simplicity over feature breadth.
- Fast checks must pass after every kept experiment.
- Preserve current add-card behavior for users who ignore the new UI.

## What's Been Tried
- Session start: identified that drag/drop already exists inside the editor and on the deck browser, but the Add Cards window does not surface this capability clearly.
- Initial hypothesis: a quick-intake surface in Add Cards can improve discoverability faster than a full LLM implementation, while a design doc can capture the larger LLM-era direction.
