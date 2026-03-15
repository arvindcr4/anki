# Autoresearch: LLM-era intake UX for Anki Add Cards

## Objective
Improve Anki's Add Cards experience for the LLM era by making source capture more discoverable, lower-friction, and better organized. Phase 1 made intake visible. Phase 2 made the banner feel complete with visible LLM status and last-source feedback. Phase 3 focuses on what the user explicitly asked for next: cards should stay neatly organized automatically whenever source material is captured.

## Metrics
- **Primary**: `source_organization_score` (unitless, higher is better)
- **Secondary**: `syntax_ok`, `auto_context_tags`, `visible_context`

## How to Run
`./autoresearch.sh`

The script performs a fast Python syntax check and then scores how well the Add Cards intake flow preserves organization automatically:
- visible current deck / note type context
- automatic `capture::inbox` tagging
- automatic source provenance tags
- automatic deck and note type context tags on every capture
- explicit organize action for manual cleanup
- status text that reminds the learner which tags were applied

## Files in Scope
- `qt/aqt/addcards.py`
- `docs/llm-intake-ux.md`
- `autoresearch.md` / `autoresearch.sh` / `autoresearch.ideas.md`

## Off Limits
- Scheduling / FSRS logic
- Rust backend / storage layer
- Reviewer flow outside what is needed to support the Add Cards prototype
- New runtime dependencies

## Constraints
- Reuse existing editor insertion logic.
- Keep changes scoped to Add Cards.
- Favor simple defaults over complex configuration.
- Fast checks must pass after every kept experiment.
- Preserve current add-card behavior for users who ignore the new UI.

## What's Been Tried
- Exposed a discoverable intake strip with drag/drop, file picking, URL pasting, LLM setup entry point, and organization action.
- Added automatic `capture::inbox` and source provenance tags on file/URL capture.
- Added visible LLM status and last-source feedback in the banner.
- Captured broader product rationale in `docs/llm-intake-ux.md`.
- Current gap: deck and note type tags are only applied when the learner explicitly presses Organize, which means source-driven notes can still land with partial metadata.
