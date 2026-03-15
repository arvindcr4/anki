# Autoresearch: Daily cards timeline on the main deck screen

## Objective
Prototype a Roam-like daily cards view on the main deck browser so learners can navigate not only by deck, but also by date. The deck browser should gain a visually clear daily timeline that groups recently added cards by day and lets the user jump straight into those cards. The UX should emphasize strong hierarchy, low cognitive load, and obvious next steps.

## Metrics
- **Primary**: `daily_cards_ux_score` (unitless, higher is better)
- **Secondary**: `timeline_surface`, `browse_by_date`, `visual_hierarchy`, `syntax_ok`

## How to Run
`./autoresearch.sh`

The script performs a fast Python syntax check and scores whether the deck browser exposes a date-oriented daily cards UX:
- daily timeline data model in deck browser rendering
- clickable browse-by-date action
- dedicated daily cards panel styling
- empty/zero state support for dates with no cards
- docs that explain the daily timeline UX

## Files in Scope
- `qt/aqt/deckbrowser.py`
- `qt/aqt/data/web/css/deckbrowser.scss`
- `docs/daily-deck-ux.md`
- `autoresearch.md` / `autoresearch.sh` / `autoresearch.ideas.md`

## Off Limits
- Scheduling / FSRS logic
- Rust backend / storage layer
- Reviewer flow
- New runtime dependencies

## Constraints
- Keep the classic deck tree intact.
- Keep the daily timeline lightweight and reversible.
- Prefer date browse affordances over heavy new workflows.
- Fast checks must pass after every kept experiment.

## What's Been Tried
- Existing work improved Add Cards capture and LLM UX.
- Current gap: the main deck screen is still organized almost entirely by deck tree. There is no date-based overview of recently created learning material.
