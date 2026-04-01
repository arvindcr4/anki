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
- clickable browse-by-date actions, including date-labeled today that upgrades to burst-day review when today dominates the week, a last-7-days action that still shows the concrete visible range, a panel-level current-gap-week shortcut when relevant, date-bounded streak, date-labeled burst-day review, resume-your-last-capture, panel-level busiest-day recovery that upgrades to burst-day review when appropriate and remains visible when burst significance overlaps with the latest session, and summary-pill shortcuts
- dedicated daily cards panel styling, including a compact 7-day activity strip with visible dates, stateful highlighting for streak/latest/busiest/current-gap states, a decoding legend, context-aware capture hints that explain burst and gap emphasis, accessible labels, discoverability hints, and assistive-tech semantics
- burst-heavy weeks should be legible both in the summary pills and directly on the relevant row/bar
- empty/zero state support for dates with no cards, including collapsed quiet stretches so repeated empty rows do not drown out active days
- card-creation affordances from the daily cards surface, including context-aware create/import actions with momentum-aware import wording, a zero-to-first-card prompt with import fallback, a capture-enabled Today bar, and a keep-capturing shortcut for Today
- momentum cues such as active/quiet day balance, consistency, gap, latest-capture metadata, visible range, pace, trend, density, burst share, streaks, busiest-day summaries, and next-step guidance so the panel encourages continuity, not just navigation, with density remaining directly browseable when users want to inspect high-card-output weeks, gap summaries calling out the latest capture date, and multi-day lulls named consistently as the current gap with their own browse target
- context-sensitive guidance and row actions so the right next step is one click away, including trend-aware restart prompts, consistency nudges, visually emphasized resume-last-capture shortcuts, current-gap recovery for both quiet days and quiet stretches, row-level resume-last-capture recovery, row-level week-context fallback, date-anchored current-gap guidance, gap-length-aware import recovery, busiest-row import followups, burst-review followups, recovery imports, and stateful guidance styling
- an insight summary with stateful styling that interprets the week before suggesting what to do next, including paused-timeline/current-gap, burst-then-gap, and just-started states, and can jump straight into the relevant date view
- overlapping row states should be preserved and remain readable when a day is both latest and busiest, including when Today is also the latest session
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
