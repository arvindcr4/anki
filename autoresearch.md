# Autoresearch: Gated source-to-LLM workflow clarity in Anki Add Cards

## Objective
Clarify the workflow so the user sees an obvious sequence: capture source first, then use LLM actions. The current banner exposes Summarize / Q&A / Cloze, but those controls remain active even when no source has been captured, and they remain stale after a note is added. The next step is to gate those actions on source state and reset them when the note resets.

## Metrics
- **Primary**: `workflow_gating_score` (unitless, higher is better)
- **Secondary**: `syntax_ok`, `gating_signals`, `reset_signals`

## How to Run
`./autoresearch.sh`

The script performs a fast Python syntax check and scores whether the Add Cards workflow is explicit and stateful:
- LLM actions exist
- LLM actions can be enabled/disabled as a group
- actions default to disabled before a source is captured
- actions are enabled when a source is captured
- source workflow resets after the note resets

## Files in Scope
- `qt/aqt/addcards.py`
- `autoresearch.md` / `autoresearch.sh` / `autoresearch.ideas.md`

## Off Limits
- Scheduling / FSRS logic
- Rust backend / storage layer
- Full provider integration
- New runtime dependencies

## Constraints
- Keep the workflow inline.
- Do not hide the existence of the LLM actions; make them visible but correctly gated.
- Reset stale source state when moving to a fresh note.
- Fast checks must pass after every kept experiment.

## What's Been Tried
- Built a visible quick-intake banner.
- Added organization defaults and source provenance tags.
- Added visible LLM workspace actions and source preview messaging.
- Current gap: the actions are not yet tied to source state. A learner can click them before capturing anything, and stale source context can linger after a new note is created.
