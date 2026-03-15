# Autoresearch: LLM workspace visibility in Anki Add Cards

## Objective
Make LLM APIs feel front and center in Anki's Add Cards flow without breaking the classic editor. The quick-intake banner already handles files, URLs, visible context, and auto-organization. The next step is to expose a small but obvious LLM workspace directly in that banner so the learner can immediately see what LLM-era actions this screen is designed around.

## Metrics
- **Primary**: `llm_workspace_score` (unitless, higher is better)
- **Secondary**: `syntax_ok`, `front_center_actions`, `preview_first_signals`

## How to Run
`./autoresearch.sh`

The script performs a fast Python syntax check and then scores whether Add Cards now surfaces an obvious LLM workspace:
- visible LLM status
- visible LLM action buttons in the intake banner
- explicit preview-first language
- dynamic LLM readiness feedback after a source is captured
- preserved file/URL capture entry points

## Files in Scope
- `qt/aqt/addcards.py`
- `docs/llm-intake-ux.md`
- `autoresearch.md` / `autoresearch.sh` / `autoresearch.ideas.md`

## Off Limits
- Scheduling / FSRS logic
- Rust backend / storage layer
- Full LLM provider integration
- New runtime dependencies

## Constraints
- Keep the Add Cards experience simple; no large modal workflow if a compact inline workspace will do.
- Reuse the current intake banner instead of inventing a second capture surface.
- Preserve the non-LLM manual path.
- Fast checks must pass after every kept experiment.

## What's Been Tried
- Added a discoverable quick-intake banner with drag/drop, file picking, URL pasting, LLM setup entry point, and organization action.
- Added visible current deck / note type context, visible LLM status, and last-source feedback.
- Added automatic `capture::inbox`, source provenance, deck, and note-type tags on every source capture.
- Captured the broader product rationale in `docs/llm-intake-ux.md`.
- Current gap: LLM setup is visible, but actual LLM-era actions are still implicit. The banner needs explicit prompt/action affordances so the user immediately understands how source capture flows into generation.
