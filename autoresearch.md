# Autoresearch: Add Cards visual polish in Anki

## Objective
Apply stronger UX and product-design principles to the source-first Add Cards workspace so it feels intentional, legible, and attractive instead of like a debug panel. The goal is better visual hierarchy, clearer affordances, better grouping, and drag feedback while preserving the fast manual path.

## Metrics
- **Primary**: `intake_ux_polish_score` (unitless, higher is better)
- **Secondary**: `visual_hierarchy`, `drag_feedback`, `context_clarity`, `syntax_ok`

## How to Run
`./autoresearch.sh`

The script performs a fast Python syntax check and scores whether the Add Cards intake surface has stronger UX polish:
- section/card grouping for source and LLM areas
- styled context chips or equivalent context emphasis
- drag-active visual feedback
- button hierarchy for primary, accent, and secondary actions
- docs mention the visual design principles

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
- Preserve the classic manual add-card path.
- Keep the interface compact enough for the Add Cards window.
- Prefer visual hierarchy and feedback over adding more controls.
- Fast checks must pass after every kept experiment.
