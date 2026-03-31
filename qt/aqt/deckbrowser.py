# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import html
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import aqt
import aqt.operations
from anki.collection import Collection, OpChanges
from anki.decks import DeckCollapseScope, DeckId, DeckTreeNode
from aqt import AnkiQt, gui_hooks
from aqt.deckoptions import display_options_for_deck_id
from aqt.operations import QueryOp
from aqt.operations.deck import (
    add_deck_dialog,
    remove_decks,
    rename_deck,
    reparent_decks,
    set_current_deck,
    set_deck_collapsed,
)
from aqt.qt import *
from aqt.sound import av_player
from aqt.toolbar import BottomBar
from aqt.utils import getOnlyText, openLink, shortcut, showInfo, tr


class DeckBrowserBottomBar:
    def __init__(self, deck_browser: DeckBrowser) -> None:
        self.deck_browser = deck_browser


@dataclass
class DailyCardsGroup:
    days_ago: int
    label: str
    date_label: str
    note_count: int
    card_count: int


@dataclass
class RenderData:
    """Data from collection that is required to show the page."""

    tree: DeckTreeNode
    current_deck_id: DeckId
    studied_today: str
    sched_upgrade_required: bool
    daily_groups: list[DailyCardsGroup]
    recent_unique_notes: int
    active_day_count: int
    busiest_days_ago: int | None
    rollover_hour: int


@dataclass
class DeckBrowserContent:
    """Stores sections of HTML content that the deck browser will be
    populated with.

    Attributes:
        tree {str} -- HTML of the deck tree section
        stats {str} -- HTML of the stats section
        daily_cards {str} -- HTML of the daily cards timeline section
    """

    tree: str
    stats: str
    daily_cards: str


@dataclass
class RenderDeckNodeContext:
    current_deck_id: DeckId


DAY_SECS = 86_400
HALF_DAY_SECS = 43_200
DAY_MS = DAY_SECS * 1000
RECENT_DAYS = 7


def _format_rollover_hour(hour: int) -> str:
    normalized = hour % 24
    suffix = "AM" if normalized < 12 else "PM"
    display_hour = normalized % 12 or 12
    return f"{display_hour} {suffix}"


def _count_label(count: int, singular: str, plural: str | None = None) -> str:
    plural = plural or f"{singular}s"
    label = singular if count == 1 else plural
    return f"{count} {label}"


def _recent_daily_card_groups(
    col: Collection, days: int = RECENT_DAYS
) -> tuple[list[DailyCardsGroup], int, int, int | None]:
    now = datetime.now().astimezone()
    tz = now.tzinfo
    assert tz is not None
    next_day_cutoff = col.sched.day_cutoff
    next_day_cutoff_ms = next_day_cutoff * 1000
    groups: list[DailyCardsGroup] = []

    for days_ago in range(days):
        midpoint = datetime.fromtimestamp(
            next_day_cutoff - (DAY_SECS * days_ago) - HALF_DAY_SECS,
            tz,
        )
        if days_ago == 0:
            label = "Today"
        elif days_ago == 1:
            label = "Yesterday"
        else:
            label = midpoint.strftime("%a")
        date_label = f"{midpoint.strftime('%b')} {midpoint.day}"
        groups.append(
            DailyCardsGroup(
                days_ago=days_ago,
                label=label,
                date_label=date_label,
                note_count=0,
                card_count=0,
            )
        )

    window_start = (next_day_cutoff - (DAY_SECS * days)) * 1000
    assert col.db is not None
    rows = col.db.all(
        """
with recent_cards as (
    select cast((? - id) / ? as integer) as days_ago, nid
    from cards
    where id > ? and id <= ?
),
summary as (
    select count(distinct nid) as recent_unique_notes
    from recent_cards
)
select recent.days_ago,
       count(*) as card_count,
       count(distinct recent.nid) as note_count,
       (select recent_unique_notes from summary) as recent_unique_notes
from recent_cards as recent
where recent.days_ago >= 0 and recent.days_ago < ?
group by recent.days_ago
order by recent.days_ago
""",
        next_day_cutoff_ms,
        DAY_MS,
        window_start,
        next_day_cutoff_ms,
        days,
    )

    recent_unique_notes = 0
    for days_ago, card_count, note_count, unique_notes in rows:
        bucket = int(days_ago)
        groups[bucket].card_count = int(card_count)
        groups[bucket].note_count = int(note_count)
        recent_unique_notes = int(unique_notes)
    active_groups = [group for group in groups if group.card_count]
    busiest_group = max(
        active_groups,
        key=lambda group: (group.card_count, group.note_count, -group.days_ago),
        default=None,
    )

    return (
        groups,
        recent_unique_notes,
        len(active_groups),
        busiest_group.days_ago if busiest_group else None,
    )


class DeckBrowser:
    _render_data: RenderData

    def __init__(self, mw: AnkiQt) -> None:
        self.mw = mw
        self.web = mw.web
        self.bottom = BottomBar(mw, mw.bottomWeb)
        self.scrollPos = QPoint(0, 0)
        self._refresh_needed = False

    def show(self) -> None:
        av_player.stop_and_clear_queue()
        self.web.set_bridge_command(self._linkHandler, self)
        # redraw top bar for theme change
        self.mw.toolbar.redraw()
        self.refresh()

    def refresh(self) -> None:
        self._renderPage()
        self._refresh_needed = False

    def refresh_if_needed(self) -> None:
        if self._refresh_needed:
            self.refresh()

    def op_executed(
        self, changes: OpChanges, handler: object | None, focused: bool
    ) -> bool:
        if (
            changes.study_queues
            or changes.note
            or changes.card
            or changes.deck
            or changes.notetype
        ) and handler is not self:
            self._refresh_needed = True

        if focused:
            self.refresh_if_needed()

        return self._refresh_needed

    # Event handlers
    ##########################################################################

    def _linkHandler(self, url: str) -> Any:
        if ":" in url:
            (cmd, arg) = url.split(":", 1)
        else:
            cmd = url
            arg = ""
        if cmd == "open":
            self.set_current_deck(DeckId(int(arg)))
        elif cmd == "opts":
            self._showOptions(arg)
        elif cmd == "shared":
            self._onShared()
        elif cmd == "import":
            self.mw.onImport()
        elif cmd == "create":
            self._on_create()
        elif cmd == "drag":
            source, target = arg.split(",")
            self._handle_drag_and_drop(DeckId(int(source)), DeckId(int(target or 0)))
        elif cmd == "collapse":
            self._collapse(DeckId(int(arg)))
        elif cmd == "v2upgrade":
            self._confirm_upgrade()
        elif cmd == "v2upgradeinfo":
            if self.mw.col.sched_ver() == 1:
                openLink("https://faqs.ankiweb.net/the-anki-2.1-scheduler.html")
            else:
                openLink("https://faqs.ankiweb.net/the-2021-scheduler.html")
        elif cmd == "select":
            set_current_deck(
                parent=self.mw, deck_id=DeckId(int(arg))
            ).run_in_background()
        elif cmd == "browseAdded":
            self._browse_added_cards(arg)
        elif cmd == "browseRecent":
            self._browse_recent_cards()
        elif cmd == "addcards":
            self.mw.onAddCard()
        elif cmd == "importcards":
            self.mw.onImport()
        elif cmd == "browseStreak":
            self._browse_streak_cards(arg)
        return False

    def set_current_deck(self, deck_id: DeckId) -> None:
        set_current_deck(parent=self.mw, deck_id=deck_id).success(
            lambda _: self.mw.onOverview()
        ).run_in_background(initiator=self)

    def _daily_group_for(self, days_ago: int) -> DailyCardsGroup | None:
        if 0 <= days_ago < len(self._render_data.daily_groups):
            return self._render_data.daily_groups[days_ago]
        return None

    def _daily_group_search(self, group: DailyCardsGroup) -> str:
        upper_bound = group.days_ago + 1
        if group.days_ago == 0:
            return f"added:{upper_bound}"
        return f"added:{upper_bound} -added:{group.days_ago}"

    def _browse_recent_cards(self) -> None:
        recent_days = len(self._render_data.daily_groups)
        browser = aqt.dialogs.open("Browser", self.mw)
        browser.search_for(
            f"added:{recent_days}",
            "Cards added in last 7 days",
        )

    def _browse_added_cards(self, key: str) -> None:
        try:
            days_ago = int(key)
        except ValueError:
            return
        if not (group := self._daily_group_for(days_ago)) or not group.card_count:
            return
        browser = aqt.dialogs.open("Browser", self.mw)
        browser.search_for(
            self._daily_group_search(group),
            f"Cards added on {group.date_label}",
        )

    def _browse_streak_cards(self, arg: str) -> None:
        try:
            start_days_ago_str, span_str = arg.split(",", 1)
            start_days_ago = int(start_days_ago_str)
            span = int(span_str)
        except ValueError:
            return
        if span <= 0:
            return
        upper_bound = start_days_ago + span
        if start_days_ago == 0:
            query = f"added:{upper_bound}"
            title = "Cards added in current streak"
        else:
            query = f"added:{upper_bound} -added:{start_days_ago}"
            title = "Cards added in last streak"
        browser = aqt.dialogs.open("Browser", self.mw)
        browser.search_for(query, title)

    # HTML generation
    ##########################################################################

    _body = """
<div class="deck-browser-shell">
<div class="deck-browser-table-wrap">
<table cellspacing=0 cellpadding=3>
%(tree)s
</table>
</div>
<div class="deck-browser-secondary-row">
%(stats)s
%(daily_cards)s
</div>
</div>
"""

    def _renderPage(self, reuse: bool = False) -> None:
        if not reuse:

            def get_data(col: Collection) -> RenderData:
                (
                    daily_groups,
                    recent_unique_notes,
                    active_day_count,
                    busiest_days_ago,
                ) = _recent_daily_card_groups(col)
                return RenderData(
                    tree=col.sched.deck_due_tree(),
                    current_deck_id=col.decks.get_current_id(),
                    studied_today=col.studied_today(),
                    sched_upgrade_required=not col.v3_scheduler(),
                    daily_groups=daily_groups,
                    recent_unique_notes=recent_unique_notes,
                    active_day_count=active_day_count,
                    busiest_days_ago=busiest_days_ago,
                    rollover_hour=int(col.conf.get("rollover", 4)),
                )

            def success(output: RenderData) -> None:
                self._render_data = output
                self.__renderPage(None)

            QueryOp(
                parent=self.mw,
                op=get_data,
                success=success,
            ).run_in_background()
        else:
            self.web.evalWithCallback("window.pageYOffset", self.__renderPage)

    def __renderPage(self, offset: int | None) -> None:
        data = self._render_data
        content = DeckBrowserContent(
            tree=self._renderDeckTree(data.tree),
            stats=self._renderStats(),
            daily_cards=self._renderDailyCards(),
        )
        gui_hooks.deck_browser_will_render_content(self, content)
        self.web.stdHtml(
            self._v1_upgrade_message(data.sched_upgrade_required)
            + self._body % content.__dict__,
            css=["css/deckbrowser.css"],
            js=[
                "js/vendor/jquery.min.js",
                "js/vendor/jquery-ui.min.js",
                "js/deckbrowser.js",
            ],
            context=self,
        )
        self._drawButtons()
        if offset is not None:
            self._scrollToOffset(offset)
        gui_hooks.deck_browser_did_render(self)

    def _scrollToOffset(self, offset: int) -> None:
        self.web.eval("window.scrollTo(0, %d, 'instant');" % offset)

    def _renderStats(self) -> str:
        return """
<div id="studiedToday" class="deck-browser-card">
  <div class="deck-browser-card-label">Studied today</div>
  <div class="deck-browser-card-value">{}</div>
</div>
""".format(self._render_data.studied_today)

    def _renderDailyCards(self) -> str:  # noqa: PLR0912
        rows: list[str] = []
        activity_bars: list[str] = []
        recent_days = len(self._render_data.daily_groups)
        total_cards = sum(group.card_count for group in self._render_data.daily_groups)
        total_notes = self._render_data.recent_unique_notes
        active_day_count = self._render_data.active_day_count
        has_recent_cards = total_cards > 0
        busiest_days_ago = self._render_data.busiest_days_ago
        busiest_group = (
            self._daily_group_for(busiest_days_ago)
            if busiest_days_ago is not None
            else None
        )
        latest_active_group = next(
            (group for group in self._render_data.daily_groups if group.card_count),
            None,
        )
        gap_summary = "Gap: no recent capture"
        if latest_active_group:
            if latest_active_group.days_ago == 0:
                gap_summary = "Gap: captured today"
            else:
                gap_summary = f"Gap: last capture {_count_label(latest_active_group.days_ago, 'day')} ago"
        gap_summary_markup = (
            f'<div class="daily-cards-pill daily-cards-gap">{gap_summary}</div>'
        )
        if latest_active_group:
            gap_summary_markup = (
                f'<a class="daily-cards-link daily-cards-pill daily-cards-gap" href=# '
                f'title="Browse latest capture" aria-label="Browse latest capture" '
                f'onclick="return pycmd(\'browseAdded:{latest_active_group.days_ago}\')">'
                f"{gap_summary}</a>"
            )
        range_summary = "Range: this week"
        if self._render_data.daily_groups:
            range_summary = (
                f"Range: {self._render_data.daily_groups[-1].date_label}"
                f" → {self._render_data.daily_groups[0].date_label}"
            )
        active_day_count_label = _count_label(active_day_count, "active day")
        quiet_day_count = max(0, recent_days - active_day_count)
        quiet_day_summary = "Quiet days: none"
        if quiet_day_count:
            quiet_day_summary = f"Quiet days: {_count_label(quiet_day_count, 'day')}"
        active_day_markup = f'<div class="daily-cards-pill daily-cards-activity">{active_day_count_label} with cards</div>'
        quiet_day_markup = f'<div class="daily-cards-pill daily-cards-quiet">{quiet_day_summary}</div>'
        range_summary_markup = (
            f'<div class="daily-cards-pill daily-cards-range">{range_summary}</div>'
        )
        if has_recent_cards:
            active_day_markup = (
                f'<a class="daily-cards-link daily-cards-pill daily-cards-activity" href=# '
                'title="Browse active week" aria-label="Browse active week" '
                'onclick="return pycmd(\'browseRecent\')">'
                f"{active_day_count_label} with cards</a>"
            )
            quiet_day_markup = (
                f'<a class="daily-cards-link daily-cards-pill daily-cards-quiet" href=# '
                'title="Browse quiet week context" aria-label="Browse quiet week context" '
                'onclick="return pycmd(\'browseRecent\')">'
                f"{quiet_day_summary}</a>"
            )
            range_summary_markup = (
                f'<a class="daily-cards-link daily-cards-pill daily-cards-range" href=# '
                'title="Browse visible week" aria-label="Browse visible week" '
                'onclick="return pycmd(\'browseRecent\')">'
                f"{range_summary}</a>"
            )
        density_summary = "Density: no cards yet"
        if total_notes:
            density_summary = f"Density: {total_cards / total_notes:.1f} cards/note"
        streak_count = 0
        streak_label = "Current streak"
        if (
            self._render_data.daily_groups
            and self._render_data.daily_groups[0].card_count
        ):
            for group in self._render_data.daily_groups:
                if not group.card_count:
                    break
                streak_count += 1
        else:
            streak_label = "Last streak"
            streak_started = False
            for group in self._render_data.daily_groups:
                if not streak_started:
                    if group.card_count:
                        streak_started = True
                        streak_count = 1
                    continue
                if not group.card_count:
                    break
                streak_count += 1
        streak_summary = f"{streak_label}: none yet"
        streak_summary_markup = (
            f'<div class="daily-cards-pill daily-cards-streak">{streak_summary}</div>'
        )
        if streak_count:
            streak_summary = f"{streak_label}: {_count_label(streak_count, 'day')}"
            if latest_active_group:
                streak_title = (
                    "Browse current streak"
                    if latest_active_group.days_ago == 0
                    else "Browse last streak"
                )
                streak_summary_markup = (
                    f'<a class="daily-cards-link daily-cards-pill daily-cards-streak" href=# '
                    f'title="{streak_title}" aria-label="{streak_title}" '
                    f'onclick="return pycmd(\'browseStreak:{latest_active_group.days_ago},{streak_count}\')">'
                    f"{streak_summary}</a>"
                )
            else:
                streak_summary_markup = f'<div class="daily-cards-pill daily-cards-streak">{streak_summary}</div>'
        heatmap_hint = "Bars light up as you create or import cards."
        if has_recent_cards:
            heatmap_hint = "Tap a bar to browse that day."
        guidance_actions: list[str] = []
        guidance = "Create or import cards to start this week's timeline."
        if (
            self._render_data.daily_groups
            and self._render_data.daily_groups[0].card_count
        ):
            guidance = (
                f"You're on a {_count_label(streak_count, 'day')} streak. "
                "Keep capturing while the topic is fresh."
            )
            guidance_actions.append(
                '<a class="daily-cards-link daily-cards-pill" href=# onclick="return pycmd(\'addcards\')">Keep the streak going</a>'
            )
            if latest_active_group:
                guidance_actions.append(
                    f'<a class="daily-cards-link daily-cards-pill" href=# onclick="return pycmd(\'browseStreak:{latest_active_group.days_ago},{streak_count}\')">Browse current streak</a>'
                )
        elif active_day_count:
            guidance = (
                f"You were active on {_count_label(active_day_count, 'day')}. "
                "Add a card today to restart the streak."
            )
            guidance_actions.append(
                '<a class="daily-cards-link daily-cards-pill" href=# onclick="return pycmd(\'addcards\')">Restart streak today</a>'
            )
            if latest_active_group:
                guidance_actions.append(
                    f'<a class="daily-cards-link daily-cards-pill" href=# onclick="return pycmd(\'browseAdded:{latest_active_group.days_ago}\')">Browse latest day</a>'
                )
        else:
            guidance_actions.append(
                '<a class="daily-cards-link daily-cards-pill" href=# onclick="return pycmd(\'addcards\')">Create first card</a>'
            )
            guidance_actions.append(
                '<a class="daily-cards-link daily-cards-pill" href=# onclick="return pycmd(\'importcards\')">Import cards</a>'
            )
        busiest_summary = "Busiest: no recent activity yet"
        busiest_summary_markup = (
            f'<div class="daily-cards-pill daily-cards-busiest">{busiest_summary}</div>'
        )
        if busiest_group:
            busiest_summary = "Busiest: {label} ({count})".format(
                label=html.escape(busiest_group.label),
                count=_count_label(busiest_group.card_count, "card"),
            )
            busiest_summary_markup = (
                f'<a class="daily-cards-link daily-cards-pill daily-cards-busiest" href=# '
                f'title="Browse busiest day" aria-label="Browse busiest day" '
                f'onclick="return pycmd(\'browseAdded:{busiest_group.days_ago}\')">'
                f"{busiest_summary}</a>"
            )
        max_cards = max(
            (group.card_count for group in self._render_data.daily_groups),
            default=0,
        )
        for group in self._render_data.daily_groups:
            bar_height = 16
            if max_cards and group.card_count:
                bar_height += int((group.card_count / max_cards) * 44)
            bar_summary = html.escape(
                f"{group.label} {group.date_label}: "
                f"{_count_label(group.card_count, 'card')} across "
                f"{_count_label(group.note_count, 'note')}"
            )
            bar_classes = ["daily-cards-bar"]
            if group.card_count:
                bar_classes.append("has-cards")
                bar_markup = (
                    f"<a class='{' '.join(bar_classes)}' style='height:{bar_height}px' "
                    f"title='{bar_summary}' aria-label='{bar_summary}' href=# "
                    f"onclick='return pycmd(\"browseAdded:{group.days_ago}\")'>"
                    f"<span class='daily-cards-bar-count'>{group.card_count}</span></a>"
                )
            else:
                bar_classes.append("is-empty")
                if group.days_ago == 0:
                    bar_classes.append("is-capture-bar")
                    create_today_summary = html.escape(
                        "Create today's first card from the activity strip"
                    )
                    bar_markup = (
                        f"<a class='{' '.join(bar_classes)}' style='height:{bar_height}px' "
                        f"title='{create_today_summary}' aria-label='{create_today_summary}' href=# "
                        f"onclick='return pycmd(\"addcards\")'>+</a>"
                    )
                else:
                    bar_markup = (
                        f"<div class='{' '.join(bar_classes)}' style='height:{bar_height}px' "
                        f"title='{bar_summary}' aria-label='{bar_summary}'></div>"
                    )
            activity_bars.append(
                """
<div class="daily-cards-bar-column">
  {bar_markup}
  <div class="daily-cards-bar-label">{label}</div>
  <div class="daily-cards-bar-date">{date_label}</div>
</div>
""".format(
                    bar_markup=bar_markup,
                    label=html.escape(group.label),
                    date_label=html.escape(group.date_label),
                )
            )
            row_classes = ["daily-cards-row"]
            status_badge = ""
            if group.days_ago == 0:
                row_classes.append("is-today")
            if (
                latest_active_group
                and group.days_ago == latest_active_group.days_ago
                and group.card_count
                and group.days_ago != 0
            ):
                row_classes.append("is-latest-session")
                status_badge = '<span class="daily-cards-status daily-cards-status-secondary">Latest session</span>'
            if group.days_ago == busiest_days_ago and group.card_count:
                row_classes.append("is-busiest")
                status_badge = '<span class="daily-cards-status">Most active</span>'
            if group.card_count:
                metrics_markup = """
  <div class="daily-cards-metric">{card_count_label}</div>
  <div class="daily-cards-metric">{note_count_label}</div>
""".format(
                    card_count_label=_count_label(group.card_count, "card"),
                    note_count_label=_count_label(group.note_count, "note"),
                )
                action = f"<a class='daily-cards-link' href=# onclick='return pycmd(\"browseAdded:{group.days_ago}\")'>Browse cards →</a>"
                row_classes.append("has-cards")
                if group.days_ago == 0:
                    action = """
<div class="daily-cards-action-stack">
  <a class='daily-cards-link' href=# onclick='return pycmd(\"browseAdded:0\")'>Browse cards →</a>
  <a class="daily-cards-link daily-cards-secondary-link" href=# onclick="return pycmd('addcards')">Create another</a>
</div>
"""
                elif latest_active_group and group.days_ago == latest_active_group.days_ago:
                    action = f"""
<div class="daily-cards-action-stack">
  <a class='daily-cards-link' href=# onclick='return pycmd(\"browseAdded:{group.days_ago}\")'>Browse cards →</a>
  <a class="daily-cards-link daily-cards-secondary-link" href=# onclick="return pycmd('addcards')">Create today</a>
</div>
"""
            else:
                row_classes.append("is-empty")
                metrics_markup = (
                    '<div class="daily-cards-empty-summary">No cards added</div>'
                )
                if group.days_ago == 0:
                    row_classes.append("is-capture-target")
                    action = "<a class='daily-cards-link' href=# onclick=\"return pycmd('addcards')\">Create first card →</a>"
                else:
                    action = '<span class="daily-cards-empty">—</span>'
            rows.append(
                """
<div class="{row_classes}">
  <div class="daily-cards-date-group">
    <div class="daily-cards-label-row">
      <div class="daily-cards-label">{label}</div>
      {status_badge}
    </div>
    <div class="daily-cards-date">{date_label}</div>
  </div>
  {metrics_markup}
  <div class="daily-cards-action">{action}</div>
</div>
""".format(
                    row_classes=" ".join(row_classes),
                    label=html.escape(group.label),
                    status_badge=status_badge,
                    date_label=html.escape(group.date_label),
                    metrics_markup=metrics_markup,
                    action=action,
                )
            )
        today_action = ""
        if self._render_data.daily_groups and self._render_data.daily_groups[0].card_count:
            today_action = (
                '<a class="daily-cards-link daily-cards-pill" href=# '
                'onclick="return pycmd(\'browseAdded:0\')">Browse today</a>'
            )
        latest_day_action = ""
        if latest_active_group and latest_active_group.days_ago > 0:
            latest_day_action = (
                f'<a class="daily-cards-link daily-cards-pill" href=# '
                f"onclick=\"return pycmd('browseAdded:{latest_active_group.days_ago}')\">"
                "Browse latest day</a>"
            )
        panel_state = """
  <div class="daily-cards-actions">
    <a class="daily-cards-link daily-cards-pill daily-cards-create" href=# onclick="return pycmd('addcards')">Create cards</a>
    <a class="daily-cards-link daily-cards-pill daily-cards-import" href=# onclick="return pycmd('importcards')">Import cards</a>
  </div>
  <div class="daily-cards-zero-state">
    Add cards today and they'll appear here for fast date-based browsing.
  </div>
"""
        if has_recent_cards:
            panel_state = """
  <div class="daily-cards-actions">
    <a class="daily-cards-link daily-cards-pill daily-cards-create" href=# onclick="return pycmd('addcards')">Create cards</a>
    <a class="daily-cards-link daily-cards-pill daily-cards-import" href=# onclick="return pycmd('importcards')">Import cards</a>
    {today_action}
    {latest_day_action}
    <a class="daily-cards-link daily-cards-pill" href=# onclick="return pycmd('browseRecent')">Browse last {recent_days} days</a>
  </div>
""".format(
                today_action=today_action,
                latest_day_action=latest_day_action,
                recent_days=recent_days,
            )
        return """
<div class="daily-cards-panel deck-browser-card">
  <div class="deck-browser-card-label">Daily cards</div>
  <div class="daily-cards-subtitle">Browse recently created cards by date, not only by deck.</div>
  <div class="daily-cards-meta">
    <div class="daily-cards-pill daily-cards-rollover">Day resets at {rollover_label}</div>
    <div class="daily-cards-pill daily-cards-summary">
      <span class="daily-cards-summary-label">Last 7 days:</span>
      <span class="daily-cards-summary-counts">{total_cards_label} across {total_notes_label}</span>
    </div>
    {active_day_markup}
    {quiet_day_markup}
    {gap_summary_markup}
    {range_summary_markup}
    <div class="daily-cards-pill daily-cards-density">{density_summary}</div>
    {streak_summary_markup}
    {busiest_summary_markup}
  </div>
  <div class="daily-cards-heatmap" role="group" aria-label="7 day activity strip">
    {activity_bars}
  </div>
  <div class="daily-cards-strip-hint">{heatmap_hint}</div>
{panel_state}  <div class="daily-cards-guidance-block" role="status" aria-live="polite">
    <div class="daily-cards-guidance">{guidance}</div>
    <div class="daily-cards-guidance-actions">{guidance_actions}</div>
  </div>
  <div class="daily-cards-list">
    {rows}
  </div>
</div>
""".format(
            rollover_label=_format_rollover_hour(self._render_data.rollover_hour),
            total_cards_label=_count_label(total_cards, "card"),
            total_notes_label=_count_label(total_notes, "note"),
            active_day_markup=active_day_markup,
            quiet_day_markup=quiet_day_markup,
            gap_summary_markup=gap_summary_markup,
            range_summary_markup=range_summary_markup,
            density_summary=density_summary,
            streak_summary_markup=streak_summary_markup,
            busiest_summary_markup=busiest_summary_markup,
            guidance=guidance,
            guidance_actions="\n".join(guidance_actions),
            heatmap_hint=heatmap_hint,
            activity_bars="\n".join(activity_bars),
            panel_state=panel_state,
            rows="\n".join(rows),
        )

    def _renderDeckTree(self, top: DeckTreeNode) -> str:
        buf = """
<tr><th colspan=5 align=start>{}</th>
<th class=count>{}</th>
<th class=count>{}</th>
<th class=count>{}</th>
<th class=optscol></th></tr>""".format(
            tr.decks_deck(),
            tr.actions_new(),
            tr.decks_learn_header(),
            tr.decks_review_header(),
        )
        buf += self._topLevelDragRow()

        ctx = RenderDeckNodeContext(current_deck_id=self._render_data.current_deck_id)

        for child in top.children:
            buf += self._render_deck_node(child, ctx)

        return buf

    def _render_deck_node(self, node: DeckTreeNode, ctx: RenderDeckNodeContext) -> str:
        if node.collapsed:
            prefix = "+"
        else:
            prefix = "−"

        def indent() -> str:
            return "&nbsp;" * 6 * (node.level - 1)

        if node.deck_id == ctx.current_deck_id:
            klass = "deck current"
        else:
            klass = "deck"

        buf = (
            "<tr class='%s' id='%d' onclick='if(event.shiftKey) return pycmd(\"select:%d\")'>"
            % (
                klass,
                node.deck_id,
                node.deck_id,
            )
        )
        # deck link
        if node.children:
            collapse = (
                "<a class=collapse href=# onclick='return pycmd(\"collapse:%d\")'>%s</a>"
                % (node.deck_id, prefix)
            )
        else:
            collapse = "<span class=collapse></span>"
        if node.filtered:
            extraclass = "filtered"
        else:
            extraclass = ""
        buf += """

        <td class=decktd colspan=5>%s%s<a class="deck %s"
        href=# onclick="return pycmd('open:%d')">%s</a></td>""" % (
            indent(),
            collapse,
            extraclass,
            node.deck_id,
            html.escape(node.name),
        )

        # due counts
        def nonzeroColour(cnt: int, klass: str) -> str:
            if not cnt:
                klass = "zero-count"
            return f'<span class="{klass}">{cnt}</span>'

        review = nonzeroColour(node.review_count, "review-count")
        learn = nonzeroColour(node.learn_count, "learn-count")

        buf += ("<td align=end>%s</td>" * 3) % (
            nonzeroColour(node.new_count, "new-count"),
            learn,
            review,
        )
        # options
        buf += (
            "<td align=center class=opts><a onclick='return pycmd(\"opts:%d\");'>"
            "<img src='/_anki/imgs/gears.svg' class=gears></a></td></tr>" % node.deck_id
        )
        # children
        if not node.collapsed:
            for child in node.children:
                buf += self._render_deck_node(child, ctx)
        return buf

    def _topLevelDragRow(self) -> str:
        return "<tr class='top-level-drag-row'><td colspan='6'>&nbsp;</td></tr>"

    # Options
    ##########################################################################

    def _showOptions(self, did: str) -> None:
        m = QMenu(self.mw)
        a = m.addAction(tr.actions_rename())
        assert a is not None
        qconnect(a.triggered, lambda b, did=did: self._rename(DeckId(int(did))))
        a = m.addAction(tr.actions_options())
        assert a is not None
        qconnect(a.triggered, lambda b, did=did: self._options(DeckId(int(did))))
        a = m.addAction(tr.actions_export())
        assert a is not None
        qconnect(a.triggered, lambda b, did=did: self._export(DeckId(int(did))))
        a = m.addAction(tr.actions_delete())
        assert a is not None
        qconnect(a.triggered, lambda b, did=did: self._delete(DeckId(int(did))))
        gui_hooks.deck_browser_will_show_options_menu(m, int(did))
        m.popup(QCursor.pos())

    def _export(self, did: DeckId) -> None:
        self.mw.onExport(did=did)

    def _rename(self, did: DeckId) -> None:
        def prompt(name: str) -> None:
            new_name = getOnlyText(
                tr.decks_new_deck_name(), default=name, title=tr.actions_rename()
            )
            if not new_name or new_name == name:
                return
            else:
                rename_deck(
                    parent=self.mw, deck_id=did, new_name=new_name
                ).run_in_background()

        QueryOp(
            parent=self.mw, op=lambda col: col.decks.name(did), success=prompt
        ).run_in_background()

    def _options(self, did: DeckId) -> None:
        display_options_for_deck_id(did)

    def _collapse(self, did: DeckId) -> None:
        node = self.mw.col.decks.find_deck_in_tree(self._render_data.tree, did)
        if node:
            node.collapsed = not node.collapsed
            set_deck_collapsed(
                parent=self.mw,
                deck_id=did,
                collapsed=node.collapsed,
                scope=DeckCollapseScope.REVIEWER,
            ).run_in_background()
            self._renderPage(reuse=True)

    def _handle_drag_and_drop(self, source: DeckId, target: DeckId) -> None:
        reparent_decks(
            parent=self.mw, deck_ids=[source], new_parent=target
        ).run_in_background()

    def _delete(self, did: DeckId) -> None:
        deck = self.mw.col.decks.find_deck_in_tree(self._render_data.tree, did)
        assert deck is not None
        deck_name = deck.name
        remove_decks(
            parent=self.mw, deck_ids=[did], deck_name=deck_name
        ).run_in_background()

    # Top buttons
    ######################################################################

    drawLinks = [
        ["", "shared", tr.decks_get_shared()],
        ["", "create", tr.decks_create_deck()],
        ["Ctrl+Shift+I", "import", tr.decks_import_file()],
    ]

    def _drawButtons(self) -> None:
        buf = ""
        drawLinks = deepcopy(self.drawLinks)
        for b in drawLinks:
            if b[0]:
                b[0] = tr.actions_shortcut_key(val=shortcut(b[0]))
            buf += """
<button title='%s' onclick='pycmd(\"%s\");'>%s</button>""" % tuple(b)
        self.bottom.draw(
            buf=buf,
            link_handler=self._linkHandler,
            web_context=DeckBrowserBottomBar(self),
        )

    def _onShared(self) -> None:
        openLink(f"{aqt.appShared}decks/")

    def _on_create(self) -> None:
        if op := add_deck_dialog(
            parent=self.mw, default_text=self.mw.col.decks.current()["name"]
        ):
            op.run_in_background()

    ######################################################################

    def _v1_upgrade_message(self, required: bool) -> str:
        if not required:
            return ""

        update_required = tr.scheduling_update_required().replace("V2", "v3")

        return f"""
<center>
<div class=callout>
    <div>
      {update_required}
    </div>
    <div>
      <button onclick='pycmd("v2upgrade")'>
        {tr.scheduling_update_button()}
      </button>
      <button onclick='pycmd("v2upgradeinfo")'>
        {tr.scheduling_update_more_info_button()}
      </button>
    </div>
</div>
</center>
"""

    def _confirm_upgrade(self) -> None:
        if self.mw.col.sched_ver() == 1:
            self.mw.col.mod_schema(check=True)
            self.mw.col.upgrade_to_v2_scheduler()
        self.mw.col.set_v3_scheduler(True)

        showInfo(tr.scheduling_update_done())
        self.refresh()
