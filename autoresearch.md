# Autoresearch: Source-to-LLM preview loop in Anki Add Cards

## Objective
Strengthen the link between dropped source material and LLM actions. The Add Cards banner now exposes Summarize, Q&A, and Cloze actions, but it still reads more like a control strip than a source-to-generation workflow. The next step is to add an explicit source preview loop so the user can see: what source is active, that an LLM workspace exists, and what the next step will be.

## Metrics
- **Primary**: `source_preview_loop_score` (unitless, higher is better)
- **Secondary**: `syntax_ok`, `source_preview_signals`, `llm_workspace_signals`

## How to Run
`./autoresearch.sh`

The script performs a fast Python syntax check and scores whether Add Cards presents a clear source-to-LLM workflow:
- explicit `LLM workspace` heading
- explicit `Source preview` surface
- visible Summarize / Q&A / Cloze actions
- next-step messaging after source capture
- dynamic preview updates when a source or action changes

## Files in Scope
- `qt/aqt/addcards.py`
- `docs/llm-intake-ux.md`
- `autoresearch.md` / `autoresearch.sh` / `autoresearch.ideas.md`

## Off Limits
- Scheduling / FSRS logic
- Rust backend / storage layer
- Full provider integration
- New runtime dependencies

## Constraints
- Keep the workflow inline and lightweight.
- No big modal wizard; the value should be visible in the banner itself.
- Preserve the classic manual editing path.
- Fast checks must pass after every kept experiment.

## What's Been Tried
- Added a discoverable quick-intake banner with visible file/url capture.
- Added auto-organization tags for source, deck, and note type.
- Added visible LLM status, last-source feedback, and front-center Summarize / Q&A / Cloze actions.
- Current gap: the active source is still described only as a status line. The UI needs an explicit source-preview surface to make the capture-to-generation loop legible at a glance.
