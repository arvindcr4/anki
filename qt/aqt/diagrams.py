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


# Inline error_html template used when a TikZ/Mermaid block fails to render.
# Surfacing the raw source + the renderer's complaint is far more useful than
# a silent failure (or a half-rendered box that leaves the user staring).
_RENDER_ERROR_HTML = (
    '<div class="diagram-error" style="border:1px solid #b91c1c;'
    'background:#fef2f2;color:#7f1d1d;padding:8px 12px;border-radius:6px;'
    'font-family:menlo,monospace;font-size:12px;white-space:pre-wrap;">'
    "<strong>{kind} render failed:</strong> {msg}\n\n"
    "<small style=\"opacity:.85\">Source:</small>\n{body}"
    "</div>"
)


def render_error_html(kind: str, body: str, msg: str) -> str:
    """Build the inline error fallback shown when a diagram fails to render.

    Used as a JS template (see _DIAGRAM_RUNNER_JS) and reachable from Python
    for any future server-side render path.
    """
    import html as _html

    return _RENDER_ERROR_HTML.format(
        kind=_html.escape(kind),
        msg=_html.escape(msg),
        body=_html.escape(body)[:1000],
    )


# ---------------------------------------------------------------------------
# Render cache — keyed by content hash, persisted in collection.media so
# rendered SVGs survive across launches and sync to AnkiMobile.
# ---------------------------------------------------------------------------


def _diagram_cache_filename(kind: str, body: str) -> str:
    """Stable filename for a (kind, body) pair, content-addressed via SHA1."""
    import hashlib

    digest = hashlib.sha1(body.strip().encode("utf-8")).hexdigest()[:16]
    safe_kind = "".join(c for c in kind.lower() if c.isalnum()) or "diag"
    return f"_anki-{safe_kind}-{digest}.svg"


def cache_diagram_svg(
    col: object,
    kind: str,
    body: str,
    svg: bytes | None = None,
) -> str:
    """Return the cache filename for a (kind, body) pair, writing svg if given.

    The filename is derived from the content hash, so two callers presenting
    the same TikZ/Mermaid source map to the same media file. ``svg`` may be
    ``None`` when the caller is only checking whether the cache already has
    a render (use ``media.have(filename)`` afterwards). When ``svg`` is
    provided and the file isn't already cached, it's written into
    ``collection.media`` so the next card that shows the same source skips
    re-rendering entirely (and the file syncs to AnkiMobile alongside other
    media).
    """
    fname = _diagram_cache_filename(kind, body)
    media = getattr(col, "media", None)
    if media is None:
        return fname
    have = getattr(media, "have", None)
    write_data = getattr(media, "write_data", None)
    try:
        if svg is not None and callable(have) and callable(write_data):
            if not have(fname):
                write_data(fname, svg)
    except Exception:  # pragma: no cover — write paths depend on backend
        # Cache-miss is a soft failure; the diagram will still render via JS.
        pass
    return fname


# ---------------------------------------------------------------------------
# Offline / vendored loader
# ---------------------------------------------------------------------------

# Version of TikZJax pinned to the install_tikzjax_assets helper. Pinning here
# makes the cache key stable across Anki launches and lets us bump the bundled
# copy explicitly.
VENDORED_TIKZJAX_VERSION = "v1"
VENDORED_TIKZJAX_URL = (
    f"https://tikzjax.com/{VENDORED_TIKZJAX_VERSION}/tikzjax.js"
)
VENDORED_TIKZJAX_FONTS_URL = (
    f"https://tikzjax.com/{VENDORED_TIKZJAX_VERSION}/fonts.css"
)
VENDORED_TIKZJAX_FILENAME = f"_anki-tikzjax-{VENDORED_TIKZJAX_VERSION}.js"
VENDORED_TIKZJAX_FONTS_FILENAME = (
    f"_anki-tikzjax-fonts-{VENDORED_TIKZJAX_VERSION}.css"
)


def install_tikzjax_assets(col: object) -> tuple[bool, str]:
    """Download TikZJax + its fonts CSS into the collection.media folder.

    Returns ``(ok, message)``. Idempotent — if both files are already present,
    skips the network round-trip. Errors during download are swallowed and
    surfaced through the ``ok`` flag rather than raising, because rendering
    must always degrade gracefully back to the CDN loader.
    """
    media = getattr(col, "media", None)
    if media is None:
        return False, "collection has no media manager"
    have = getattr(media, "have", None)
    write_data = getattr(media, "write_data", None)
    if not callable(have) or not callable(write_data):
        return False, "media manager missing have/write_data"

    if have(VENDORED_TIKZJAX_FILENAME) and have(VENDORED_TIKZJAX_FONTS_FILENAME):
        return True, "already installed"

    import urllib.error
    import urllib.request

    targets = [
        (VENDORED_TIKZJAX_URL, VENDORED_TIKZJAX_FILENAME),
        (VENDORED_TIKZJAX_FONTS_URL, VENDORED_TIKZJAX_FONTS_FILENAME),
    ]
    for url, fname in targets:
        if have(fname):
            continue
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                data = resp.read()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            # error path — leave whatever was already cached intact
            return False, f"download failed for {fname}: {exc}"
        try:
            write_data(fname, data)
        except Exception as exc:  # pragma: no cover - depends on backend
            return False, f"could not write {fname}: {exc}"

    return True, "installed"


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
  function _ankiDiagramFallback(el, kind, msg) {
    try {
      const body = (el.textContent || '').trim();
      const wrap = document.createElement('div');
      wrap.className = 'diagram-error';
      wrap.style.cssText =
        'border:1px solid #b91c1c;background:#fef2f2;color:#7f1d1d;' +
        'padding:8px 12px;border-radius:6px;font-family:menlo,monospace;' +
        'font-size:12px;white-space:pre-wrap;';
      wrap.innerHTML =
        '<strong>' + kind + ' render failed:</strong> ' +
        (msg || '(no message)') +
        '\n\n<small style="opacity:.85">Source:</small>\n' +
        body.replace(/&/g, '&amp;').replace(/</g, '&lt;');
      if (el.parentNode) el.parentNode.replaceChild(wrap, el);
    } catch (_) { /* swallow — fallback must never throw */ }
  }
  if (haveMer) {
    if (window._ankiMermaid) {
      try {
        const result = window._ankiMermaid.run({
          querySelector: 'div.mermaid:not([data-processed])',
          suppressErrors: true,
        });
        if (result && typeof result.catch === 'function') {
          result.catch(function (e) {
            document.querySelectorAll('div.mermaid:not([data-processed])').forEach(function (el) {
              _ankiDiagramFallback(el, 'Mermaid', e && e.message || String(e));
            });
          });
        }
      } catch (e) {
        console.warn('mermaid.run failed:', e);
        document.querySelectorAll('div.mermaid:not([data-processed])').forEach(function (el) {
          _ankiDiagramFallback(el, 'Mermaid', e && e.message || String(e));
        });
      }
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
