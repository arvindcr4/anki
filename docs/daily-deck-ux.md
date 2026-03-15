# Daily cards UX on the main deck screen

## Goal

The deck browser should help learners navigate by **time** as well as by **deck**. A Roam-like daily cards panel makes recent learning material feel easier to revisit, especially when a user is capturing notes from ongoing research.

## UX principles

This prototype follows common guidance from strong UX systems and books:

1. **Recognition over recall** — users should see recent days immediately instead of remembering which deck or tag they used.
2. **Clear information scent** — each day row should answer: what day is this, how many cards were created, and what happens if I click it?
3. **Progressive disclosure** — the classic deck tree remains intact, while the daily timeline adds a second lightweight lens.
4. **Visual hierarchy** — deck stats and daily cards should feel like distinct cards, not a flat wall of text.
5. **Low cognitive load** — Today and Yesterday deserve stronger emphasis than older days.

## Proposed interaction

- Keep the deck tree as the primary study structure.
- Add a **Daily cards** panel beside or below the existing summary card.
- Show recent days in descending order.
- Add a compact **Last 7 days** summary so users instantly understand whether the panel is active and worth exploring.
- Surface the rollover explicitly with a small hint like **Day resets at 4 AM** so users understand why late-night cards stay grouped together.
- Present the rollover hint and week summary as a compact meta row of pills so the panel scans quickly before the user reads the day-by-day list.
- Split the week summary into a short range label plus a separate counts segment, so the sentence reads cleanly while still emphasizing the totals.
- Keep card and note labels grammatically correct for one-item days, so the interface never shows awkward copy like **1 cards**.
- Keep the week summary honest by counting unique notes across the full range, not by naively summing each day bucket.
- For each day, show:
  - a human label like **Today**, **Yesterday**, or weekday
  - the date
  - card count
  - note count
  - a direct **Browse cards** action that opens an exact added-day search
- If a day has no cards, keep the row visible and show a soft empty state such as **No cards added**.
- When the panel has activity, offer a panel-level shortcut like **Browse last 7 days** for users who want a broad date-based view before drilling into a specific day.
- If the whole week is empty, show a reassuring panel-level hint: **Add cards today and they'll appear here**.

## Why this helps

When users are doing research-heavy note creation, they often remember *when* they made something before they remember *which deck* they filed it into. A date-oriented surface gives them another intuitive path through the collection without replacing Anki's existing structure.

The panel should also refresh after note and card changes, so the date view feels trustworthy instead of stale. Browse actions should target the exact added-day card search, and the displayed day buckets should follow Anki's scheduler cutoff instead of plain midnight, so the UI wording and the Browser results stay aligned.
