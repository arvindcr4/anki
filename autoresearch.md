# Autoresearch: Add Cards discoverability in Anki

## Objective
Users are missing the new source-first intake because it only appears after opening Add Cards. Improve discoverability from the main app entrypoint so it is obvious where the drag-and-drop + LLM workspace lives.

## Metrics
- **Primary**: `entrypoint_discoverability_score` (unitless, higher is better)
- **Secondary**: `toolbar_affordance`, `window_title_signal`, `docs_signal`, `syntax_ok`

## How to Run
`./autoresearch.sh`

The script checks whether the source-first Add Cards prototype is easier to find:
- toolbar affordance explicitly mentions capture/source-first behavior
- Add Cards window title signals capture/intake behavior
- docs mention where to find the prototype
- Python syntax still passes

## Files in Scope
- `qt/aqt/toolbar.py`
- `qt/aqt/addcards.py`
- `docs/llm-intake-ux.md`
- `autoresearch.md` / `autoresearch.sh`

## Off Limits
- Scheduling / FSRS logic
- Rust backend / storage layer
- Real provider/network integration
- New runtime dependencies

## Constraints
- Keep changes scoped to finding/opening Add Cards.
- Preserve the classic add-note path.
- Prefer obvious inline labels/tooltips over extra modal flows.
- Fast checks must pass after every kept experiment.
