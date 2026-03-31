#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 - <<'PY'
from pathlib import Path
import py_compile

py_compile.compile('qt/aqt/deckbrowser.py', doraise=True)
texts = []
for candidate in [
    Path('qt/aqt/deckbrowser.py'),
    Path('qt/aqt/data/web/css/deckbrowser.scss'),
    Path('docs/daily-deck-ux.md'),
]:
    if candidate.exists():
        texts.append(candidate.read_text())
joined = '\n'.join(texts)
score = 0
timeline_surface = 0
browse_by_date = 0
visual_hierarchy = 0
capture_support = 0
query_efficiency = 0
checks = [
    ('DailyCardsGroup', 3, 'timeline'),
    ('daily-cards-panel', 2, 'timeline'),
    ('daily-cards-heatmap', 2, 'visual'),
    ('daily-cards-bar', 2, 'visual'),
    ('daily-cards-bar-label', 1, 'visual'),
    ('daily-cards-bar-count', 1, 'visual'),
    ('aria-label', 2, 'visual'),
    ('cards across', 2, 'timeline'),
    ('daily-cards-row', 2, 'visual'),
    ('browseAdded', 3, 'browse'),
    ('browseRecent', 2, 'browse'),
    ('browseStreak', 2, 'browse'),
    ('added:', 3, 'browse'),
    ('No cards added', 1, 'timeline'),
    ('daily-cards-empty-summary', 1, 'visual'),
    ('0 cards / 0 notes', 1, 'timeline'),
    ('deck-browser-secondary-row', 1, 'visual'),
    ('Daily cards', 1, 'docs'),
    ('date-oriented', 1, 'docs'),
    ('daily-cards-summary', 2, 'visual'),
    ('daily-cards-rollover', 2, 'visual'),
    ('daily-cards-meta', 2, 'visual'),
    ('daily-cards-pill', 1, 'visual'),
    ('daily-cards-summary-label', 1, 'visual'),
    ('daily-cards-summary-counts', 1, 'visual'),
    ('is-empty', 1, 'visual'),
    ('_count_label', 2, 'visual'),
    ('grammatically correct', 1, 'timeline'),
    ('Day resets at', 1, 'timeline'),
    ("Add cards today and they'll appear here", 2, 'timeline'),
    ('changes.note', 1, 'timeline'),
    ('changes.card', 1, 'timeline'),
    ('Browse cards', 1, 'browse'),
    ('Browse cards →', 2, 'browse'),
    ('rows="\n".join(rows)', 2, 'visual'),
    ('Browse last 7 days', 2, 'browse'),
    ('Browse latest day', 2, 'browse'),
    ('latest_active_group', 1, 'timeline'),
    ('Cards added on', 1, 'browse'),
    ('Cards added in last 7 days', 1, 'browse'),
    ('scheduler cutoff', 2, 'timeline'),
    ('unique notes across the full range', 1, 'timeline'),
    ('Last 7 days:', 1, 'visual'),
    ('Create cards', 2, 'capture'),
    ('Import cards', 2, 'capture'),
    ('addcards', 2, 'capture'),
    ('importcards', 2, 'capture'),
    ('daily-cards-create', 1, 'capture'),
    ('daily-cards-import', 1, 'capture'),
    ('Most active', 1, 'visual'),
    ('Latest session', 2, 'visual'),
    ('is-latest-session', 1, 'visual'),
    ('daily-cards-status', 1, 'visual'),
    ('daily-cards-status-secondary', 1, 'visual'),
    ('active day', 2, 'timeline'),
    ('daily-cards-gap', 1, 'visual'),
    ('Gap:', 2, 'timeline'),
    ('captured today', 1, 'timeline'),
    ('last capture', 1, 'timeline'),
    ('daily-cards-range', 1, 'visual'),
    ('Range:', 2, 'timeline'),
    ('daily-cards-density', 1, 'visual'),
    ('Density:', 2, 'timeline'),
    ('cards/note', 2, 'timeline'),
    ('Current streak', 2, 'timeline'),
    ('Last streak', 2, 'timeline'),
    ('daily-cards-streak', 1, 'visual'),
    ('daily-cards-guidance', 2, 'timeline'),
    ('daily-cards-guidance-block', 1, 'visual'),
    ('daily-cards-guidance-actions', 2, 'capture'),
    ('daily-cards-strip-hint', 1, 'visual'),
    ('Tap a bar to browse that day', 2, 'timeline'),
    ('Bars light up as you create or import cards', 2, 'timeline'),
    ('Keep capturing while the topic is fresh', 2, 'timeline'),
    ('Keep the streak going', 2, 'capture'),
    ('restart the streak', 2, 'timeline'),
    ('Restart streak today', 2, 'capture'),
    ('start this week\'s timeline', 2, 'timeline'),
    ('Busiest:', 2, 'timeline'),
    ('Browse current streak', 2, 'browse'),
    ('Browse last streak', 2, 'browse'),
    ('Browse busiest day', 2, 'browse'),
    ('Create first card', 2, 'capture'),
    ('Create another', 2, 'capture'),
    ('daily-cards-action-stack', 1, 'capture'),
    ('daily-cards-secondary-link', 1, 'visual'),
    ('is-capture-target', 1, 'visual'),
    ('count(distinct nid)', 2, 'query'),
    ('with recent_cards as', 2, 'query'),
    ('summary as', 1, 'query'),
    ('group by days_ago', 1, 'query'),
]
for needle, pts, bucket in checks:
    if needle in joined:
        score += pts
        if bucket == 'timeline':
            timeline_surface += 1
        elif bucket == 'browse':
            browse_by_date += 1
        elif bucket == 'visual':
            visual_hierarchy += 1
        elif bucket == 'docs':
            visual_hierarchy += 1
        elif bucket == 'capture':
            capture_support += 1
        elif bucket == 'query':
            query_efficiency += 1
print(f'METRIC daily_cards_ux_score={score}')
print('METRIC syntax_ok=1')
print(f'METRIC timeline_surface={timeline_surface}')
print(f'METRIC browse_by_date={browse_by_date}')
print(f'METRIC visual_hierarchy={visual_hierarchy}')
print(f'METRIC capture_support={capture_support}')
print(f'METRIC query_efficiency={query_efficiency}')
PY
