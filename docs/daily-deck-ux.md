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
- Show the explicit date range for the visible week so **Last 7 days** is grounded in real calendar dates, not just an abstract relative label.
- Add a compact **Gap** summary that tells the learner how long it has been since the last capture session.
- When the latest capture is not today, anchor that gap summary to the actual capture date as well, so the learner can verify the jump target without scanning the rows.
- When the gap spans multiple days, name it explicitly as a **Current gap** in the summary row so the top-level pills use the same recovery language as the strip and row states.
- Add a separate browseable **Latest** summary pill too, so the most recent active day stays visible in the metadata row even when the gap pill is focused on recovery language.
- Include that latest session’s card count in the pill, so the metadata row reveals not only when the freshest session happened but also whether it was a tiny capture or a substantial batch.
- When the freshest session is also the busiest one, let the **Latest** pill say so directly instead of making the learner cross-reference the separate busiest-day pill.
- Make the **Gap**, **active days**, and **visible range** pills browseable so the summary row doubles as navigation instead of passive metadata.
- Add accessible labels to the browseable summary pills and expose the guidance area as a polite status region so the panel reads clearly in assistive tech, not just visually.
- Present the rollover hint and week summary as a compact meta row of pills so the panel scans quickly before the user reads the day-by-day list.
- Split the week summary into a short range label plus a separate counts segment, so the sentence reads cleanly while still emphasizing the totals.
- Add a compact 7-day activity strip so learners can scan recent capture volume before reading the detailed rows.
- Carry streak, latest-session, busiest-day, and current-gap cues into the strip itself so the mini-visualization is not just decorative volume bars.
- Add a tiny legend under the strip so users can decode those bar states without guessing what the highlighting means, including when empty bars represent the current gap rather than older quiet history.
- Include each strip bar’s date under the day label so the week can be read at a glance without relying on hover alone.
- Make the activity strip self-explanatory with hover and assistive labels that include the day, date, and cards-across-notes summary.
- Add a tiny helper line under the strip so users immediately understand that bars are browseable, that they summarize cards-across-notes for each day, and that empty bars will light up as they create or import cards.
- When a current gap is present, let that helper line call out the dashed empty bars explicitly so the learner can decode the lull without reading the row list first.
- When the week is burst-heavy, let that same helper line explain that the highlighted burst bar marks the busiest session, so the strip can teach its own emphasis without relying on the legend alone.
- Make the empty **Today** bar itself a lightweight **create first card** target, so the visual strip can start a capture flow instead of only reflecting past activity.
- Add compact momentum pills for **active days**, **quiet days**, **consistency percentage**, **cards-per-note density**, **cards-per-active-day pace**, **trend**, **burst share**, **current/last streak**, and **busiest day** so learners can tell at a glance whether their recent capture streak is healthy.
- Show **consistency percentage** so learners can judge week-over-week capture reliability without mentally converting active and quiet day counts into a ratio.
- Show **trend** to indicate whether recent capture is rising, steady, cooling, or just starting, instead of forcing the learner to mentally compare the strip bars.
- Show **burst share** to reveal whether the week reflects steady capture or one dominant import/generation session.
- Show **cards-per-active-day pace** so the panel reveals recent capture intensity even when the week has only a few active days.
- Show **quiet days** explicitly so the panel makes gaps in capture behavior visible, not just productive days.
- Show **cards-per-note density** to help users distinguish broad note capture from denser card generation such as cloze-heavy sessions or big imports.
- Make that density pill browseable too, so users can jump from a surprising cards-per-note ratio straight into the visible week context.
- Make the streak pill browseable so momentum is not just decorative: users can reopen the cards from their current or last active run.
- Make the **busiest day** summary pill directly browseable so the highest-volume capture session doubles as a quick re-entry point.
- When that busiest day is not also the latest session, keep a panel-level **Browse busiest day** shortcut in the action row so high-volume import/generation sessions remain one click away.
- If the visible week is burst-heavy, promote that same top-row shortcut to **Review burst day** so the panel explains why that specific day matters before the user clicks.
- Pair it with a **burst** pill that quantifies how much of the visible week came from that single day.
- When the week is burst-heavy, offer a **Review burst day** action so users can revisit the dominant session before generating more material.
- Carry that same **Review burst day** language down into the dominant row’s primary CTA, so the row itself explains why that day is worth revisiting instead of falling back to a generic browse label.
- Mirror burst-heavy weeks in the strip and row badges with a **Burst session** marker so users can spot the dominant day without cross-referencing the summary pills.
- Follow those metrics with a short guidance sentence that answers the next-step question: keep capturing, restart the streak today, or start this week’s timeline.
- Add a short **Insight** line above the guidance actions so the panel explains what kind of week this is: a single burst, a rising trend, cooling activity, a paused timeline with a current gap, a burst followed by a current gap, a week that just started moving, or steady consistency.
- Make that insight itself browseable so users can jump from the interpretation straight into the relevant burst day, latest capture, or recent trend view.
- Give that insight line stateful styling so bursty, rising, cooling, and consistent weeks are visually distinguishable before the user reads the full sentence.
- Pair that guidance with context-sensitive actions so the banner can directly offer **Keep the streak going**, **Restart streak today**, **Browse current streak**, or **Create first card** depending on the learner’s recent activity.
- Give that guidance block lightweight stateful styling too, so recovery, burst, just-started, and consistency states are visually legible before the learner reads the full sentence.
- Let the guidance react to the weekly trend as well: for example, suggest **Extend rising trend** when momentum is building, or **Reverse cooling trend** when activity is fading.
- When the trend is cooling, pair the restart CTA with **Import to rebuild momentum** so the user can recover with either manual capture or a larger generated/imported batch.
- When the week is already highly consistent but today is blank, switch to a **Keep consistency going** prompt so the user understands the main risk is breaking continuity, not lack of momentum.
- If the deck has slipped into a multi-day current gap, let the guidance call that out directly with the latest capture date, so recovery reads like resuming a paused timeline instead of a generic restart.
- Keep card and note labels grammatically correct for one-item days, so the interface never shows awkward copy like **1 cards**.
- Keep the week summary honest by counting unique notes across the full range, not by naively summing each day bucket.
- Use database-side aggregation for the week summary and per-day buckets so the deck browser stays responsive even after large imports.
- Prefer a single recent-cards aggregation query over multiple round trips where possible, so richer timeline summaries do not make the deck browser feel sluggish.
- Keep visible **Create cards** and **Import cards** actions in the panel so the main screen supports both revisiting and generating learning material.
- Let the primary create CTA adapt to context: **Create first card** for empty weeks, **Restart today** when today is blank but recent capture exists, and **Create another** when today already has cards.
- Let the import CTA adapt too: keep **Import cards** for empty weeks, use **Import more** when capture is already active, and switch to **Import to rebuild momentum** when the visible week shows a longer current gap.
- For each day, show:
  - a human label like **Today**, **Yesterday**, or weekday
  - the date
  - card count
  - note count
  - a direct **Browse cards** action that opens an exact added-day search
- If a day has no cards, keep the row visible and show a soft empty state such as **No cards added**, but visually de-emphasize it so active days stand out first.
- Avoid dumping raw **0 cards / 0 notes** rows throughout the week; that reads like database output instead of useful guidance.
- Collapse consecutive empty non-today rows into a single **Quiet stretch** summary instead of repeating **No cards added** over and over, which reduces noise when most of the week is blank.
- If that quiet stretch reaches up to yesterday, make the row itself a recovery point with **Restart after quiet stretch**, so a user can jump straight back into capture from the place where momentum visibly stopped.
- If the current gap is only yesterday, give that single quiet row a matching **Restart after quiet day** action instead of leaving the row as passive empty history.
- Pair current-gap rows with **Resume last capture** so users can either restart today or jump straight back to the most recent active session from the same recovery surface.
- Mark that leading quiet stretch as the **Current gap** so learners can tell at a glance whether the lull is the present problem or just an older part of the week.
- When that current gap is already several days long, pair the restart CTA with **Import to rebuild momentum** so recovery supports both one-card restarts and bigger catch-up bursts.
- Treat the empty **Today** row specially: turn it into a light **Create first card →** prompt so a blank day becomes an invitation to capture, not a dead end.
- Pair that empty-today prompt with **Import cards** so starting a new day supports both small manual capture and larger generated/imported sessions.
- When the week already has activity, also pair that empty-today row with **Resume last capture** so a blank today can still reconnect the learner to the freshest session without forcing them to hunt elsewhere in the panel.
- When Today already has cards, keep the row bi-directional: users should be able to **Browse cards →** and also **Create another** without leaving the same context.
- If Today is also the burst-dominant session, add **Import more** to that same row so large generation/import workflows can continue from the freshest capture context.
- When the panel has activity, offer a panel-level shortcut like **Browse last 7 days** for users who want a broad date-based view before drilling into a specific day.
- Prefer a visible-range label on that shortcut so the week-level action is anchored to concrete dates, not just a relative count.
- If today already has cards, surface a top-level **Browse today** shortcut because that is often the fastest way to revisit the freshest generated material.
- Include today’s date in that shortcut label so the action still makes sense around late-night rollover boundaries.
- If today is empty but the week is not, surface a **Browse latest day** shortcut so users can jump back to their most recent capture session.
- If the visible week is currently defined by a multi-day lull, add a panel-level **Browse current gap week** shortcut too, so users can review the whole stalled stretch without losing the broader date-based lens.
- Include the latest session’s date in that shortcut label, so the user can verify the jump target without cross-referencing the strip first.
- In the guidance area, phrase that same recovery action as **Resume last capture** so the next step feels like continuing momentum, not just browsing history.
- Give that recovery affordance a little more visual emphasis than a generic metadata pill, so missed-today users can spot the way back in quickly.
- Also mark that most recent active row as **Latest session** so the user can find it at a glance without scanning dates.
- Even when that latest row is **Today**, keep the **Latest session** meaning available; Today should not erase the fact that this is the freshest capture session.
- If the latest session is also the busiest day, show both badges instead of forcing one to win, so the row preserves both meanings.
- Render multiple badges with real spacing so stacked row states stay readable instead of collapsing into a tight blob.
- When the latest session is not today, pair its browse action with **Create today** so the user can turn yesterday’s momentum into a fresh capture session immediately.
- Let that latest row’s primary CTA read **Resume last capture →** instead of a generic browse label, so the freshest non-today session clearly feels like the recovery path back into the same work.
- Pair that browse shortcut with a persistent **Create cards** CTA so users can immediately turn a new idea into study material.
- Make active rows feel more actionable with a stronger CTA label such as **Browse cards →**.
- Mark the busiest row with a light **Most active** badge so the user can find the biggest capture session without rereading every line.
- If that busiest row is not today’s latest session, pair its browse action with **Import more** so large import/generation bursts can continue directly from the same row.
- Render row separators with real HTML newlines instead of literal **\n** text so the timeline never shows spacer artifacts between days.
- If the whole week is empty, show a reassuring panel-level hint: **Add cards today and they'll appear here**.

## Why this helps

When users are doing research-heavy note creation, they often remember _when_ they made something before they remember _which deck_ they filed it into. A date-oriented surface gives them another intuitive path through the collection without replacing Anki's existing structure.

The panel should also refresh after note and card changes, so the date view feels trustworthy instead of stale. Browse actions should target the exact added-day card search, and the displayed day buckets should follow Anki's scheduler cutoff instead of plain midnight, so the UI wording and the Browser results stay aligned.

A lightweight create-cards shortcut on the same surface closes the loop: users can notice a burst of recent research, open the capture flow, and generate more cards without leaving the deck browser first.

rows="
".join(rows)

For example, a user studying Kaplan GRE flashcards from the Play Store might want to see how many they added today.

- Kaplan GRE flashcards are a great fit for the daily cards timeline.

- To validate the timeline scale, we should test by downloading the Kaplan GRE app from an APK store, extracting its flashcards, and importing them all at once.
