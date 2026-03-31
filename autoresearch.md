# Autoresearch: Daily cards timeline on the main deck screen

## Objective

Prototype a Roam-like daily cards view on the main deck browser so learners can navigate not only by deck, but also by date. The deck browser should gain a visually clear daily timeline that groups recently added cards by day and lets the user jump straight into those cards. The UX should emphasize strong hierarchy, low cognitive load, obvious next steps, and a lightweight path back into card creation.

## Metrics

- **Primary**: `daily_cards_ux_score` (unitless, higher is better)
- **Secondary**: `timeline_surface`, `browse_by_date`, `visual_hierarchy`, `capture_support`, `query_efficiency`, `syntax_ok`

## How to Run

`./autoresearch.sh`

The script performs a fast Python syntax check and scores whether the deck browser exposes a date-oriented daily cards UX:

- daily timeline data model in deck browser rendering
- clickable browse-by-date actions, including date-labeled today, week-range, resume-your-last-capture, streak, busiest-day, and summary-pill shortcuts
- dedicated daily cards panel styling, including a compact 7-day activity strip with visible dates, stateful highlighting, a decoding legend, capture hints, accessible labels, discoverability hints, and assistive-tech semantics
- empty/zero state support for dates with no cards, without noisy repeated zero-count pills
- card-creation affordances from the daily cards surface, including create/import actions, a zero-to-first-card prompt, a capture-enabled Today bar, and a keep-capturing shortcut for Today
- momentum cues such as active/quiet day balance, gap, visible range, pace, density, burst share, streaks, busiest-day summaries, and next-step guidance so the panel encourages continuity, not just navigation
- context-sensitive guidance and row actions so the right next step is one click away
- overlapping row states should be preserved and remain readable when a day is both latest and busiest
- database-side aggregation so the week summary stays lightweight, ideally with a single recent-cards aggregation query
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
- Improve responsiveness where possible; do not trade away correctness for a benchmark bump.
- Fast checks must pass after every kept experiment.

## What's Been Tried

- Existing work improved Add Cards capture and LLM UX.
- Current gap: the main deck screen is still organized almost entirely by deck tree. There is no date-based overview of recently created learning material.
- New gap to close: the daily cards surface should help users both revisit what they added and jump back into creating more cards without slowing the deck browser on large imports.
