# Autoresearch: Detailed source preview in Anki Add Cards

## Objective
Improve the source preview so it is not just a generic summary line. After capture, the user should be able to see a small inline breakdown of what was captured — filenames or hostnames plus the tags/context inferred from them. This should make the workflow feel more concrete and organized.

## Metrics
- **Primary**: `source_detail_score` (unitless, higher is better)
- **Secondary**: `syntax_ok`, `detail_visibility`, `tag_visibility`, `reset_behavior`

## How to Run
`./autoresearch.sh`

The script performs a fast Python syntax check and scores whether Add Cards shows a richer source preview:
- dedicated source detail surface
- source detail update helper
- source details reset with a fresh note
- visible inferred tags / context in the preview area

## Files in Scope
- `qt/aqt/addcards.py`
- `docs/llm-intake-ux.md`
- `autoresearch.md` / `autoresearch.sh` / `autoresearch.ideas.md`

## Off Limits
- Scheduling / FSRS logic
- Rust backend / storage layer
- Real provider/network integration
- New runtime dependencies

## Constraints
- Keep the source detail view compact.
- Prefer inline visibility over modal inspection.
- Preserve the classic manual editing path.
- Fast checks must pass after every kept experiment.

## What's Been Tried
- Added a source-first banner, LLM workspace, source preview loop, Codex connection path, and provider preference.
- Current gap: source preview still compresses the captured material into one sentence. The user cannot quickly inspect the concrete sources/tags that were inferred without reading the status copy.
