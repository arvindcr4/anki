# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Browser-side diagram rendering for Anki cards.

Recognised tags inside any field/template:

    [tikz]   ... [/tikz]      → rendered by TikZJax (WebAssembly LaTeX)
    [mermaid]... [/mermaid]   → rendered by Mermaid.js

Why not just inject <script> tags into the card HTML?
The reviewer updates card content via `_showQuestion(...)` which uses
`innerHTML` under the hood — and <script> tags inserted via innerHTML do
NOT execute. So we instead:
  1. Rewrite [tikz]/[mermaid] tags to placeholder elements at card-render
     time (gui_hooks.card_will_show).
  2. After each card is shown (gui_hooks.reviewer_did_show_question /
     _did_show_answer), run a JS snippet in the webview that lazily loads
     the libraries via document.createElement('script') and asks them to
     process any unprocessed placeholders.
"""

from __future__ import annotations

import re

import aqt
from anki.cards import Card
from aqt import gui_hooks

_TIKZ_RE = re.compile(r"\[tikz\](.+?)\[/tikz\]", re.DOTALL | re.IGNORECASE)
_MERMAID_RE = re.compile(r"\[mermaid\](.+?)\[/mermaid\]", re.DOTALL | re.IGNORECASE)


def _wrap_tikz(match: re.Match[str]) -> str:
    body = match.group(1).strip()
    if r"\begin{tikzpicture}" not in body:
        body = "\\begin{tikzpicture}\n" + body + "\n\\end{tikzpicture}"
    if r"\begin{document}" not in body:
        body = "\\begin{document}\n" + body + "\n\\end{document}"
    # TikZJax processes <script type="text/tikz"> blocks.
    return f'<script type="text/tikz">\n{body}\n</script>'


def _wrap_mermaid(match: re.Match[str]) -> str:
    body = match.group(1).strip()
    return f'<div class="mermaid">\n{body}\n</div>'


def transform_card_html(html: str, _card: Card | None = None, _kind: str = "") -> str:
    """gui_hooks.card_will_show callback — rewrites diagram tags to placeholders."""
    if _TIKZ_RE.search(html):
        html = _TIKZ_RE.sub(_wrap_tikz, html)
    if _MERMAID_RE.search(html):
        html = _MERMAID_RE.sub(_wrap_mermaid, html)
    return html


# JS that runs in the reviewer webview after each card show. Lazily loads
# TikZJax + Mermaid the first time a card needs them, then asks the loaded
# libraries to (re-)process unprocessed placeholders.
_DIAGRAM_RUNNER_JS = r"""
(function () {
  const haveTikz = !!document.querySelector('script[type="text/tikz"]');
  const haveMer  = !!document.querySelector('div.mermaid:not([data-processed])');
  if (!haveTikz && !haveMer) return;

  // ---------- Mermaid ----------
  if (haveMer) {
    if (window._ankiMermaid) {
      try {
        window._ankiMermaid.run({
          querySelector: 'div.mermaid:not([data-processed])',
          suppressErrors: true,
        });
      } catch (e) { console.warn('mermaid.run failed:', e); }
    } else if (!window._ankiMermaidLoading) {
      window._ankiMermaidLoading = true;
      const m = document.createElement('script');
      m.type = 'module';
      m.textContent =
        "import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';" +
        "window._ankiMermaid = mermaid;" +
        "mermaid.initialize({startOnLoad: false, securityLevel: 'loose'," +
        " theme: window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'default'});" +
        "mermaid.run({querySelector: 'div.mermaid:not([data-processed])', suppressErrors: true});";
      document.head.appendChild(m);
    }
  }

  // ---------- TikZJax ----------
  if (haveTikz) {
    if (window._ankiTikzReady) {
      // TikZJax replaces script blocks in-place when its main script loads;
      // for newly-injected blocks we need to dispatch a DOMContentLoaded so
      // its bundled scanner runs again. Fall back to manual scan if exposed.
      try {
        if (typeof window.process_tikz === 'function') {
          window.process_tikz();
        } else {
          document.dispatchEvent(new Event('DOMContentLoaded'));
        }
      } catch (e) { console.warn('tikz reprocess failed:', e); }
    } else if (!window._ankiTikzLoading) {
      window._ankiTikzLoading = true;
      const css = document.createElement('link');
      css.rel = 'stylesheet';
      css.type = 'text/css';
      css.href = 'https://tikzjax.com/v1/fonts.css';
      document.head.appendChild(css);
      const tj = document.createElement('script');
      tj.src = 'https://tikzjax.com/v1/tikzjax.js';
      tj.onload = function () {
        window._ankiTikzReady = true;
        // TikZJax auto-scans on load; nothing more to do for the first card.
      };
      tj.onerror = function () { console.warn('TikZJax failed to load'); };
      document.head.appendChild(tj);
    }
  }
})();
"""


def _run_in_reviewer(_card: Card | None = None) -> None:
    web = getattr(aqt.mw, "web", None)
    if web is not None:
        web.eval(_DIAGRAM_RUNNER_JS)


def setup_hook() -> None:
    """Register the card_will_show transformer and post-show JS runner.

    Idempotent — safe to call more than once.
    """
    if transform_card_html not in gui_hooks.card_will_show._hooks:  # type: ignore[attr-defined]
        gui_hooks.card_will_show.append(transform_card_html)
    if _run_in_reviewer not in gui_hooks.reviewer_did_show_question._hooks:  # type: ignore[attr-defined]
        gui_hooks.reviewer_did_show_question.append(_run_in_reviewer)
    if _run_in_reviewer not in gui_hooks.reviewer_did_show_answer._hooks:  # type: ignore[attr-defined]
        gui_hooks.reviewer_did_show_answer.append(_run_in_reviewer)
