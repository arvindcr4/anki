# Autoresearch: LLM-era intake UX for Anki Add Cards

## Objective
Improve Anki's Add Cards experience for the LLM era by making source capture more discoverable, lower-friction, and better organized. Phase 1 established a visible quick-intake strip and captured the product rationale in docs. Phase 2 is about making the flow feel more complete: the learner should see LLM readiness, current organization context, and the last captured source at a glance.

## Metrics
- **Primary**: `llm_intake_flow_score` (unitless, higher is better)
- **Secondary**: `syntax_ok` (Python compile check), `research_doc_ready` (design guidance captured), `organization_support` (visible organization affordances), `llm_status_surface` (visible LLM status)

## How to Run
`./autoresearch.sh`

The script performs a fast Python syntax check on the in-scope Python files and then scores the current implementation against the target UX:
- discoverable drop zone / quick intake surface
- explicit file + URL capture entry points
- visible LLM setup affordance
- visible LLM status / readiness surface
- visible organization affordances for deck / note type / tags
- visible last-source feedback after capture
- source-aware tagging / guidance
- design research captured in repo docs

## Files in Scope
- `qt/aqt/addcards.py` — Add Cards window orchestration; intake banner, buttons, drop zone, and organization helpers.
- `qt/aqt/forms/addcards.ui` — layout shell for Add Cards; may need spacing or placement adjustments.
- `qt/aqt/editor.py` — existing paste/URL/file insertion logic reused by the intake surface.
- `docs/llm-intake-ux.md` — research-backed product notes for a simpler LLM-era learning flow.
- `autoresearch.md` / `autoresearch.sh` / `autoresearch.ideas.md` — experiment context, benchmark harness, and backlog.

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
- Built a quick-intake strip in `qt/aqt/addcards.py` with a discoverable drop zone, file picker, URL prompt, LLM setup entry point, and organization action.
- Reused existing editor insertion logic (`urlToLink()` + `doPaste()`) instead of creating a second media ingestion path.
- Added automatic `capture::inbox` and `source::...` tags so source-driven notes have immediate provenance metadata.
- Added `docs/llm-intake-ux.md` to capture the broader product direction for a source-first, preview-first LLM workflow.
- Current focus: make the prototype feel more complete by exposing LLM readiness and recent-source feedback directly in the banner, instead of only in helper copy.
