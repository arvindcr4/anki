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

import hashlib
import html
import re
from typing import Any

import aqt
from anki.cards import Card
from aqt import gui_hooks


def _tikz_cache_key(render_body: str) -> str:
    return hashlib.sha1(render_body.encode("utf-8")).hexdigest()[:16]

_TIKZ_RE = re.compile(r"\[tikz\](.+?)\[/tikz\]", re.DOTALL | re.IGNORECASE)
_MERMAID_RE = re.compile(r"\[mermaid\](.+?)\[/mermaid\]", re.DOTALL | re.IGNORECASE)
_FENCE_RE = re.compile(r"^```(?:tikz|latex|tex)?\s*|\s*```$", re.IGNORECASE)
_TIKZ_MARKER_RE = re.compile(r"\[/?tikz\]", re.IGNORECASE)
_TIKZPICTURE_RE = re.compile(
    r"\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}", re.DOTALL
)


# Inline error_html template used when a TikZ/Mermaid block fails to render.
# Surfacing the raw source + the renderer's complaint is far more useful than
# a silent failure (or a half-rendered box that leaves the user staring).
_RENDER_ERROR_HTML = (
    '<div class="diagram-error" style="border:1px solid #b91c1c;'
    "background:#fef2f2;color:#7f1d1d;padding:8px 12px;border-radius:6px;"
    'font-family:menlo,monospace;font-size:12px;white-space:pre-wrap;">'
    "<strong>{kind} render failed:</strong> {msg}\n\n"
    '<small style="opacity:.85">Source:</small>\n{body}'
    "</div>"
)


def _strip_nested_tikz_markers(body: str) -> str:
    def replace(match: re.Match[str]) -> str:
        prefix = body[max(0, match.start() - 20) : match.start()].lower()
        if prefix.endswith(r"\documentclass"):
            return match.group(0)
        return ""

    return _TIKZ_MARKER_RE.sub(replace, body)


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
VENDORED_TIKZJAX_URL = f"https://tikzjax.com/{VENDORED_TIKZJAX_VERSION}/tikzjax.js"
VENDORED_TIKZJAX_FONTS_URL = f"https://tikzjax.com/{VENDORED_TIKZJAX_VERSION}/fonts.css"
VENDORED_TIKZJAX_ENGINE_BASE_URL = "https://s3.us-east-2.amazonaws.com/tikzjax.com"
VENDORED_TIKZJAX_WASM_FILENAME = "3f69afb974a1e83f66a36f7618f88a38c254034b.wasm"
VENDORED_TIKZJAX_DATA_FILENAME = "b565ab0b474e8e557d954694b7379a57db669ac9.gz"
VENDORED_TIKZJAX_FILENAME = f"_anki-tikzjax-{VENDORED_TIKZJAX_VERSION}.js"
VENDORED_TIKZJAX_FONTS_FILENAME = f"_anki-tikzjax-fonts-{VENDORED_TIKZJAX_VERSION}.css"
_TIKZJAX_FONT_URL_RE = re.compile(r"url\(['\"]?\.\./bakoma/ttf/([^'\")]+)['\"]?\)")
_END_DOCUMENT_RE = re.compile(r"\s*\\end\{document\}\s*$")


def _rewrite_tikzjax_font_urls(css: bytes) -> bytes:
    """Make downloaded TikZJax CSS usable from Anki's media root."""
    text = css.decode("utf-8")
    text = _TIKZJAX_FONT_URL_RE.sub(r"url('https://tikzjax.com/bakoma/ttf/\1')", text)
    return text.encode("utf-8")


def _rewrite_tikzjax_engine_urls(js: bytes) -> bytes:
    """Make TikZJax load its WebAssembly engine from Anki media."""
    text = js.decode("utf-8")
    text = text.replace(
        f'var s="{VENDORED_TIKZJAX_ENGINE_BASE_URL}"',
        "var s=window.location.origin",
    )
    return text.encode("utf-8")


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

    if (
        have(VENDORED_TIKZJAX_FILENAME)
        and have(VENDORED_TIKZJAX_FONTS_FILENAME)
        and have(VENDORED_TIKZJAX_WASM_FILENAME)
        and have(VENDORED_TIKZJAX_DATA_FILENAME)
    ):
        return True, "already installed"

    import urllib.error
    import urllib.request

    targets = [
        (VENDORED_TIKZJAX_URL, VENDORED_TIKZJAX_FILENAME),
        (VENDORED_TIKZJAX_FONTS_URL, VENDORED_TIKZJAX_FONTS_FILENAME),
        (
            f"{VENDORED_TIKZJAX_ENGINE_BASE_URL}/{VENDORED_TIKZJAX_WASM_FILENAME}",
            VENDORED_TIKZJAX_WASM_FILENAME,
        ),
        (
            f"{VENDORED_TIKZJAX_ENGINE_BASE_URL}/{VENDORED_TIKZJAX_DATA_FILENAME}",
            VENDORED_TIKZJAX_DATA_FILENAME,
        ),
    ]
    failures: list[str] = []
    for url, fname in targets:
        if have(fname):
            continue
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                data = resp.read()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            # Don't bail on the first failure — keep going so partially-cached
            # installs (e.g., js+css already there but wasm missing) can recover
            # one missing file at a time on subsequent runs.
            failures.append(f"{fname}: {exc}")
            continue
        if fname == VENDORED_TIKZJAX_FONTS_FILENAME:
            data = _rewrite_tikzjax_font_urls(data)
        elif fname == VENDORED_TIKZJAX_FILENAME:
            data = _rewrite_tikzjax_engine_urls(data)
        try:
            write_data(fname, data)
        except Exception as exc:  # pragma: no cover - depends on backend
            failures.append(f"{fname}: write failed: {exc}")
            continue

    if failures:
        return False, "; ".join(failures)
    return True, "installed"


def _install_tikzjax_assets_for_collection(col: object) -> None:
    taskman = getattr(getattr(aqt, "mw", None), "taskman", None)
    if taskman is None:
        return

    def task() -> tuple[bool, str]:
        return install_tikzjax_assets(col)

    def on_done(future: object) -> None:
        try:
            ok, message = future.result()
        except Exception as exc:  # pragma: no cover - defensive Qt callback guard
            print(f"TikZJax asset install failed: {exc}")
            return
        if not ok:
            print(f"TikZJax asset install skipped: {message}")

    taskman.run_in_background(task, on_done, uses_collection=False)


def _drop_incomplete_trailing_tikz_line(body: str) -> str:
    lines = body.rstrip().splitlines()
    while lines:
        tail = lines[-1].strip()
        if not tail or tail.startswith("%"):
            lines.pop()
            continue
        if tail.endswith((";", "}")) or tail.startswith(r"\end"):
            break
        # LLM responses are sometimes truncated mid-command, e.g. "\node at (3.5,".
        # Leaving that line in makes jsTeX wait for input and the render never finishes.
        lines.pop()
        break
    return "\n".join(lines).rstrip()


def normalize_tikz_source(source: str) -> str:
    """Normalize raw LLM/user TikZ into a full TikZJax LaTeX document."""
    body = _FENCE_RE.sub("", source.strip()).strip()
    tag_match = _TIKZ_RE.search(body)
    if tag_match:
        body = tag_match.group(1).strip()
    body = _strip_nested_tikz_markers(body).strip()

    if r"\begin{tikzpicture}" not in body:
        body = "\\begin{tikzpicture}\n" + body + "\n\\end{tikzpicture}"
    elif r"\end{tikzpicture}" not in body:
        body = _END_DOCUMENT_RE.sub("", body.strip())
        body = _drop_incomplete_trailing_tikz_line(body)
        body = body.rstrip() + "\n\\end{tikzpicture}"
    if r"\begin{document}" not in body:
        body = "\\begin{document}\n" + body + "\n\\end{document}"
    elif r"\end{document}" not in body:
        body = body.rstrip() + "\n\\end{document}"
    if r"\documentclass" not in body:
        body = (
            "\\documentclass[tikz]{standalone}\n"
            "\\usepackage{tikz}\n"
            "\\usetikzlibrary{arrows.meta,positioning,calc,shapes,patterns,"
            "decorations.pathreplacing}\n" + body
        )
    return body


def tikzjax_script_source(source: str) -> str:
    """Return a TikZ picture suitable for TikZJax's script block.

    TikZJax wraps the script body with its own LaTeX document, so passing our
    normalized standalone preamble produces a duplicate ``\\documentclass``
    error. The persisted/source view remains a complete document, but the
    render script receives only the ``tikzpicture`` environment.
    """
    if match := _TIKZPICTURE_RE.search(source):
        return match.group(0).strip()
    body = _END_DOCUMENT_RE.sub("", source.strip())
    body = re.sub(r"\\documentclass(?:\[[^\]]+\])?\{[^}]+\}\s*", "", body)
    body = re.sub(r"\\usepackage(?:\[[^\]]+\])?\{[^}]+\}\s*", "", body)
    body = re.sub(r"\\usetikzlibrary\{[^}]+\}\s*", "", body)
    body = re.sub(r"\\begin\{document\}\s*", "", body)
    return body.strip()


def tikz_tag(source: str) -> str:
    """Return a persisted [tikz] tag with normalized LaTeX/TikZ content."""
    return f"[tikz]{normalize_tikz_source(source)}[/tikz]"


def _wrap_tikz(match: re.Match[str]) -> str:
    body = normalize_tikz_source(match.group(1))
    render_body = tikzjax_script_source(body)
    escaped_body = html.escape(body)
    cache_key = _tikz_cache_key(render_body)
    cached_svg = _cached_svg(cache_key)
    if cached_svg is not None:
        # Cache hit — the renderer already produced this SVG. Inline it
        # instead of emitting an <img>, so cached diagrams use the same DOM
        # path as freshly-rendered diagrams and do not depend on an extra
        # webview image fetch.
        stage_html = cached_svg
        canvas_state = "ready"
    else:
        # Cache miss — fall back to live TikZJax compile; the bulk renderer
        # or live-capture path will persist the SVG so future cards hit.
        stage_html = f'<script type="text/tikz">\n{render_body}\n</script>'
        canvas_state = "loading"
    # TikZJax processes <script type="text/tikz"> blocks.
    return (
        f'<figure class="anki-tikz-canvas" data-anki-tikz-state="{canvas_state}" '
        f'data-anki-tikz-hash="{cache_key}" '
        'data-anki-tikz-mode="fit" aria-label="TikZ diagram">'
        '<figcaption class="anki-tikz-toolbar" aria-label="TikZ controls">'
        '<button type="button" class="anki-tikz-tool" data-anki-tikz-action="fit" '
        'title="Fit to card" aria-label="Fit to card">⤢</button>'
        '<button type="button" class="anki-tikz-tool" data-anki-tikz-action="actual" '
        'title="Actual size" aria-label="Actual size">1:1</button>'
        '<button type="button" class="anki-tikz-tool" data-anki-tikz-action="source" '
        'title="Show source" aria-label="Show source">{}</button>'
        '<button type="button" class="anki-tikz-tool" data-anki-tikz-action="copy" '
        'title="Copy source" aria-label="Copy source">⧉</button>'
        '<button type="button" class="anki-tikz-tool" data-anki-tikz-action="svg" '
        'title="Save SVG" aria-label="Save SVG">⇩</button>'
        "</figcaption>"
        '<div class="anki-tikz-stage">'
        f"{stage_html}"
        "</div>"
        f'<template class="anki-tikz-source-data">{escaped_body}</template>'
        '<pre class="anki-tikz-source" hidden></pre>'
        "</figure>"
    )


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

  function _ankiTikzSource(canvas) {
    const tpl = canvas && canvas.querySelector('template.anki-tikz-source-data');
    return tpl ? (tpl.content ? tpl.content.textContent : tpl.textContent) || '' : '';
  }
  function _ankiFallbackCopy(text) {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); } catch (_) { /* ignored */ }
    ta.remove();
  }
  function _ankiInstallTikzCanvasControls() {
    if (window._ankiTikzCanvasControlsInstalled) return;
    window._ankiTikzCanvasControlsInstalled = true;
    document.addEventListener('click', function (event) {
      const button = event.target && event.target.closest
        ? event.target.closest('.anki-tikz-tool')
        : null;
      if (!button) return;
      const canvas = button.closest('.anki-tikz-canvas');
      if (!canvas) return;
      const action = button.getAttribute('data-anki-tikz-action');
      if (action === 'fit' || action === 'actual') {
        canvas.setAttribute('data-anki-tikz-mode', action);
        return;
      }
      if (action === 'source') {
        const panel = canvas.querySelector('.anki-tikz-source');
        if (!panel) return;
        if (!panel.textContent) panel.textContent = _ankiTikzSource(canvas);
        const show = panel.hasAttribute('hidden');
        panel.toggleAttribute('hidden', !show);
        button.setAttribute('aria-pressed', show ? 'true' : 'false');
        return;
      }
      if (action === 'copy') {
        const source = _ankiTikzSource(canvas);
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(source).catch(function () { _ankiFallbackCopy(source); });
        } else {
          _ankiFallbackCopy(source);
        }
        button.setAttribute('data-anki-tikz-pulse', 'copied');
        window.setTimeout(function () { button.removeAttribute('data-anki-tikz-pulse'); }, 900);
        return;
      }
      if (action === 'svg') {
        const svg = canvas.querySelector('svg');
        if (!svg) return;
        const blob = new Blob([new XMLSerializer().serializeToString(svg)], { type: 'image/svg+xml' });
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = 'anki-tikz.svg';
        link.click();
        window.setTimeout(function () { URL.revokeObjectURL(link.href); }, 1000);
      }
    });
  }
  _ankiInstallTikzCanvasControls();

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
      const canvas = kind === 'TikZ' && el.closest ? el.closest('.anki-tikz-canvas') : null;
      if (canvas) {
        canvas.setAttribute('data-anki-tikz-state', 'error');
        const stage = canvas.querySelector('.anki-tikz-stage');
        if (stage) {
          stage.innerHTML = '';
          stage.appendChild(wrap);
        } else {
          canvas.appendChild(wrap);
        }
      } else if (el.parentNode) {
        el.parentNode.replaceChild(wrap, el);
      }
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
    function _ankiApplyCachedTikz() {
      // For each canvas whose hash is already rendered (via the preload pump
      // or a prior view of the same card), splice the cached SVG straight
      // into the stage and skip TikZJax for that canvas.
      const cache = window._ankiTikzCache || {};
      document.querySelectorAll('.anki-tikz-canvas[data-anki-tikz-hash]').forEach(function (canvas) {
        const key = canvas.getAttribute('data-anki-tikz-hash');
        const cached = cache[key];
        if (!cached) return;
        const stage = canvas.querySelector('.anki-tikz-stage');
        if (!stage) return;
        const script = stage.querySelector('script[type="text/tikz"]');
        if (!script) return;  // already rendered
        stage.innerHTML = cached;
        canvas.setAttribute('data-anki-tikz-state', 'ready');
      });
    }
    function _ankiRefreshTikzCanvases() {
      const cache = window._ankiTikzCache = window._ankiTikzCache || {};
      document.querySelectorAll('.anki-tikz-canvas').forEach(function (canvas) {
        const stage = canvas.querySelector('.anki-tikz-stage');
        if (canvas.querySelector('script[type="text/tikz"]')) {
          canvas.setAttribute('data-anki-tikz-state', 'loading');
        } else {
          const svg = stage && stage.querySelector('svg');
          if (svg) {
            canvas.setAttribute('data-anki-tikz-state', 'ready');
            const key = canvas.getAttribute('data-anki-tikz-hash');
            if (key && !cache[key]) {
              cache[key] = svg.outerHTML;
              if (typeof pycmd === 'function') {
                try {
                  pycmd('anki-tikz-cache:' + JSON.stringify({h: key, s: svg.outerHTML}));
                } catch (e) { /* swallow */ }
              }
            }
          }
        }
      });
    }
    _ankiApplyCachedTikz();
    function _ankiTrackTikzCompletion() {
      // First TikZJax render has to fetch a ~10MB engine, decompress it,
      // and warm a WASM LaTeX runtime; on slow hardware this can run past
      // 20s easily. Poll every 500ms so we flip to "ready" the instant
      // each canvas is swapped, and only declare failure at 60s.
      _ankiRefreshTikzCanvases();
      const interval = window.setInterval(function () {
        _ankiRefreshTikzCanvases();
        const pending = document.querySelectorAll(
          '.anki-tikz-canvas script[type="text/tikz"]'
        );
        if (pending.length === 0) {
          window.clearInterval(interval);
        }
      }, 500);
      window.setTimeout(function () {
        window.clearInterval(interval);
        document.querySelectorAll('.anki-tikz-canvas script[type="text/tikz"]').forEach(function (el) {
          _ankiDiagramFallback(el, 'TikZ', 'TikZJax did not finish rendering');
        });
      }, 180000);
    }
    function _ankiRunTikzjaxScanner() {
      try {
        let result = null;
        if (typeof window.process_tikz === 'function') {
          result = window.process_tikz();
        } else if (typeof window.onload === 'function') {
          result = window.onload(new Event('load'));
        } else {
          document.dispatchEvent(new Event('DOMContentLoaded'));
        }
        if (result && typeof result.catch === 'function') {
          result.catch(function (e) {
            document.querySelectorAll('script[type="text/tikz"]').forEach(function (el) {
              _ankiDiagramFallback(el, 'TikZ', e && e.message || String(e));
            });
          });
        }
      } catch (e) {
        console.warn('tikz reprocess failed:', e);
        document.querySelectorAll('script[type="text/tikz"]').forEach(function (el) {
          _ankiDiagramFallback(el, 'TikZ', e && e.message || String(e));
        });
      }
    }
    function _ankiSoon(fn) {
      if (typeof window.requestIdleCallback === 'function') {
        window.requestIdleCallback(fn, { timeout: 500 });
      } else {
        window.setTimeout(fn, 50);
      }
    }
    const tikzFontsUrls = [
      %r,
      'https://tikzjax.com/v1/fonts.css',
    ];
    const tikzScriptUrls = [
      %r,
      'https://tikzjax.com/v1/tikzjax.js',
    ];
    function _ankiLoadTikzAsset(index) {
      const css = document.createElement('link');
      css.rel = 'stylesheet';
      css.type = 'text/css';
      css.href = tikzFontsUrls[index];
      document.head.appendChild(css);

      const tj = document.createElement('script');
      tj.src = tikzScriptUrls[index];
      tj.onload = function () {
        window._ankiTikzReady = true;
        _ankiRunTikzjaxScanner();
        _ankiTrackTikzCompletion();
      };
      tj.onerror = function () {
        css.remove();
        if (index + 1 < tikzScriptUrls.length) {
          _ankiLoadTikzAsset(index + 1);
        } else {
          document.querySelectorAll('script[type="text/tikz"]').forEach(function (el) {
            _ankiDiagramFallback(el, 'TikZ', 'TikZJax failed to load');
          });
        }
      };
      document.head.appendChild(tj);
    }
    if (window._ankiTikzReady) {
      // TikZJax replaces script blocks in-place when its main script loads;
      // for newly-injected blocks we need to dispatch a DOMContentLoaded so
      // its bundled scanner runs again. Fall back to manual scan if exposed.
      _ankiSoon(function () {
        _ankiRunTikzjaxScanner();
        _ankiTrackTikzCompletion();
      });
    } else if (!window._ankiTikzLoading) {
      window._ankiTikzLoading = true;
      _ankiTrackTikzCompletion();
      _ankiSoon(function () { _ankiLoadTikzAsset(0); });
    }
  }
})();
""" % (f"/{VENDORED_TIKZJAX_FONTS_FILENAME}", f"/{VENDORED_TIKZJAX_FILENAME}")

_QUEUED_DIAGRAM_RUNNER_JS = (
    "(function () {\n"
    "  const runDiagrams = function () {\n"
    f"{_DIAGRAM_RUNNER_JS}\n"
    "  };\n"
    "  if (typeof window._queueAction === 'function') {\n"
    "    window._queueAction(runDiagrams);\n"
    "  } else {\n"
    "    window.setTimeout(runDiagrams, 0);\n"
    "  }\n"
    "})();"
)


# Fire-and-forget loader that pulls TikZJax + its fonts into the reviewer
# webview as soon as the page is up, so the first card containing
# [tikz]…[/tikz] doesn't pay the ~10MB wasm/gz fetch + LaTeX warmup cost.
# Cards swap via web.eval() within the same page, so once loaded the engine
# stays hot for every subsequent card in the session.
_TIKZJAX_PREWARM_JS = r"""
(function () {
  window._ankiTikzCache = window._ankiTikzCache || {};
  if (window._ankiPrewarmTikzScripts) {
    /* already installed */
  } else {
    function ensureHiddenStage() {
      let host = document.getElementById('_anki-tikz-prewarm');
      if (host) return host;
      host = document.createElement('div');
      host.id = '_anki-tikz-prewarm';
      host.setAttribute('aria-hidden', 'true');
      host.style.cssText = 'position:fixed;left:-99999px;top:0;width:1px;'
        + 'height:1px;overflow:hidden;pointer-events:none;opacity:0;';
      document.body.appendChild(host);
      // Capture SVGs as TikZJax finishes each script in the hidden stage.
      const observer = new MutationObserver(function (mutations) {
        mutations.forEach(function (m) {
          m.addedNodes.forEach(function (node) {
            if (!(node instanceof Element)) return;
            const svgs = node.tagName === 'svg' ? [node] : node.querySelectorAll('svg');
            svgs.forEach(function (svg) {
              const wrap = svg.closest('[data-anki-prewarm-hash]');
              if (!wrap) return;
              const key = wrap.getAttribute('data-anki-prewarm-hash');
              if (key && !window._ankiTikzCache[key]) {
                window._ankiTikzCache[key] = svg.outerHTML;
                if (typeof pycmd === 'function') {
                  try {
                    pycmd('anki-tikz-cache:' + JSON.stringify({h: key, s: svg.outerHTML}));
                  } catch (e) { /* swallow */ }
                }
              }
            });
          });
        });
      });
      observer.observe(host, { childList: true, subtree: true });
      return host;
    }
    window._ankiPrewarmTikzScripts = function (specs) {
      if (!Array.isArray(specs) || specs.length === 0) return;
      const host = ensureHiddenStage();
      let added = 0;
      specs.forEach(function (spec) {
        const key = spec && spec.hash;
        const source = spec && spec.source;
        if (!key || !source) return;
        if (window._ankiTikzCache[key]) return;  // already rendered
        if (host.querySelector('[data-anki-prewarm-hash="' + key + '"]')) return;
        const wrap = document.createElement('div');
        wrap.setAttribute('data-anki-prewarm-hash', key);
        const script = document.createElement('script');
        script.type = 'text/tikz';
        script.text = source;
        wrap.appendChild(script);
        host.appendChild(wrap);
        added++;
      });
      if (added > 0) {
        function kick() {
          // TikZJax v1's bundle does not expose window.process_tikz; it only
          // installs an async window.onload handler that iterates every
          // script[type="text/tikz"] in the document and compiles each one.
          // Invoke it directly when the engine bundle is loaded so the
          // hidden-stage prewarm scripts actually render into the SVG cache.
          if (window._ankiTikzReady && typeof window.onload === 'function') {
            try {
              const p = window.onload(new Event('load'));
              if (p && typeof p.catch === 'function') {
                p.catch(function () { /* swallow — surfaces in DOM cache */ });
              }
            } catch (e) { /* swallow */ }
          } else if (typeof window.process_tikz === 'function') {
            try { window.process_tikz(); } catch (e) { /* swallow */ }
          } else {
            window.setTimeout(kick, 250);
          }
        }
        kick();
      }
    };
  }
  if (window._ankiTikzReady || window._ankiTikzLoading) { return; }
  window._ankiTikzLoading = true;
  const css = document.createElement('link');
  css.rel = 'stylesheet';
  css.type = 'text/css';
  css.href = %r;
  document.head.appendChild(css);
  const tj = document.createElement('script');
  tj.src = %r;
  tj.onload = function () { window._ankiTikzReady = true; };
  tj.onerror = function () { window._ankiTikzLoading = false; };
  document.head.appendChild(tj);
})();
""" % (f"/{VENDORED_TIKZJAX_FONTS_FILENAME}", f"/{VENDORED_TIKZJAX_FILENAME}")


def prewarm_diagram_engines(web: Any) -> None:
    """Eval the TikZJax prewarm into ``web`` if the assets are installed.

    Called from ``Reviewer.show()`` after ``stdHtml`` so the LaTeX engine
    starts fetching/compiling while the user is looking at the first card,
    instead of waiting until a [tikz] block appears.
    """
    if web is None:
        return
    try:
        col = getattr(aqt.mw, "col", None)
        media = getattr(col, "media", None) if col is not None else None
        have = getattr(media, "have", None) if media is not None else None
        if not callable(have):
            return
        if not (
            have(VENDORED_TIKZJAX_FILENAME)
            and have(VENDORED_TIKZJAX_FONTS_FILENAME)
        ):
            return
        web.eval(_TIKZJAX_PREWARM_JS)
    except Exception:
        return


# ----------------------------------------------------------- upcoming preload


_PRELOAD_LOOKAHEAD = 5
_preload_in_flight = False


def _iter_tikz_specs(card_html: str, seen: set[str]) -> list[dict[str, str]]:
    specs: list[dict[str, str]] = []
    for match in _TIKZ_RE.finditer(card_html):
        body = normalize_tikz_source(match.group(1))
        render_body = tikzjax_script_source(body)
        key = _tikz_cache_key(render_body)
        if key in seen:
            continue
        seen.add(key)
        specs.append({"hash": key, "source": render_body})
    return specs


def _collect_upcoming_tikz_specs(col: Any) -> list[dict[str, str]]:
    """Peek at the next few queued cards and pull every unique tikz body.

    Idempotent — uses ``get_queued_cards`` which the v3 scheduler explicitly
    documents as non-mutating. Renders templates for each peeked card so
    [tikz]…[/tikz] blocks can be extracted before the user advances to them.
    """
    try:
        sched = getattr(col, "sched", None)
        if sched is None or not hasattr(sched, "get_queued_cards"):
            return []
        info = sched.get_queued_cards(fetch_limit=_PRELOAD_LOOKAHEAD + 1)
    except Exception:
        return []
    queued = list(getattr(info, "cards", []) or [])
    if len(queued) <= 1:
        return []
    upcoming = queued[1 : _PRELOAD_LOOKAHEAD + 1]
    seen: set[str] = set()
    specs: list[dict[str, str]] = []
    for qc in upcoming:
        try:
            card = Card(col)
            card._load_from_backend_card(qc.card)
            out = card.render_output()
            for html_part in (out.question_text or "", out.answer_text or ""):
                specs.extend(_iter_tikz_specs(html_part, seen))
        except Exception:
            continue
    return specs


def preload_upcoming_diagrams(_card: Card | None = None) -> None:
    """Background-pump tikz from the next 5 cards into the prewarm cache.

    Hooked into ``reviewer_did_show_question`` so as soon as the user sees a
    card, we go fetch & compile tikz pictures for whatever's next. Subsequent
    cards' [tikz] blocks then resolve from cache (instant) instead of waiting
    on TikZJax's per-picture LaTeX compile.
    """
    global _preload_in_flight
    mw = aqt.mw
    if mw is None:
        return
    web = getattr(mw, "web", None)
    if web is None:
        return
    if _preload_in_flight:
        return
    _preload_in_flight = True

    from aqt.operations import QueryOp

    def done(specs: list[dict[str, str]]) -> None:
        global _preload_in_flight
        _preload_in_flight = False
        if not specs:
            return
        import json as _json

        payload = _json.dumps(specs)
        # Ensure prewarm scaffolding is installed, then push the specs.
        web.eval(_TIKZJAX_PREWARM_JS + f"\nwindow._ankiPrewarmTikzScripts({payload});")

    def failed(_exc: Exception) -> None:
        global _preload_in_flight
        _preload_in_flight = False

    try:
        QueryOp(
            parent=mw, op=_collect_upcoming_tikz_specs, success=done
        ).failure(failed).run_in_background()
    except Exception:
        _preload_in_flight = False


def _run_in_reviewer(_card: Card | None = None) -> None:
    web = getattr(aqt.mw, "web", None)
    if web is not None:
        web.eval(_QUEUED_DIAGRAM_RUNNER_JS)


# --------------------------------------------------------- persistent cache


_persistent_cache: Any = None
_bulk_renderer: Any = None


def _persistent_cache_for(mw: Any) -> Any:
    global _persistent_cache
    if _persistent_cache is not None:
        return _persistent_cache
    try:
        from aqt.tikz_cache import TikzImageCache

        folder = mw.pm.profileFolder()
        _persistent_cache = TikzImageCache(folder)
    except Exception:
        _persistent_cache = None
    return _persistent_cache


def _cached_svg(cache_key: str) -> str | None:
    """Return cached SVG markup for ``cache_key`` if it is on disk.

    ``_wrap_tikz`` calls this on every card render. The cache is built
    lazily. If it doesn't exist yet (e.g. profile not yet open), no
    cache hits, fall back to live render.
    """
    mw = aqt.mw
    if mw is None:
        return None
    cache = _persistent_cache_for(mw)
    if cache is None:
        return None
    try:
        get = getattr(cache, "get", None)
        if callable(get):
            return get(cache_key)
        return None
    except Exception:
        return None


def push_persistent_cache_to_web(web: Any) -> None:
    """Initialise the in-page cache table.

    With the on-disk image cache, cache hits are emitted as ``<img>`` tags
    directly by ``_wrap_tikz``, so the JS cache is only used for live
    captures during the current session. Just ensure the dict exists.
    """
    if web is None:
        return
    web.eval("window._ankiTikzCache = window._ankiTikzCache || {};")


def _handle_webview_cache_message(
    handled: tuple[bool, Any], cmd: str, _context: Any
) -> tuple[bool, Any]:
    """Capture ``anki-tikz-cache:<json>`` pycmd notifications to disk.

    Fired by the runner JS and preload pump whenever they observe a fresh
    SVG. We write it to ``<profile>/tikz-cache/<hash>.svg`` so the next
    time this card is rendered, ``_wrap_tikz`` emits a direct ``<img>``.
    """
    if handled[0]:
        return handled
    if not isinstance(cmd, str) or not cmd.startswith("anki-tikz-cache:"):
        return handled
    payload = cmd.split(":", 1)[1]
    mw = aqt.mw
    cache = _persistent_cache_for(mw) if mw is not None else None
    if cache is None:
        return (True, None)
    try:
        import json as _json

        obj = _json.loads(payload)
        key = obj.get("h")
        svg = obj.get("s")
        if isinstance(key, str) and isinstance(svg, str):
            cache.add(key, svg)
    except Exception:
        pass
    return (True, None)


def _start_bulk_render(_col: Any | None = None) -> None:
    """On profile/collection open, kick off the background bulk renderer.

    Scans every note for [tikz]…[/tikz], diffs against the on-disk cache,
    and feeds anything missing into a hidden webview that renders them in
    the background. Persists each SVG as soon as it's ready so progress
    survives if the user quits Anki mid-pass.
    """
    global _bulk_renderer
    mw = aqt.mw
    if mw is None or mw.col is None:
        return
    cache = _persistent_cache_for(mw)
    if cache is None:
        return
    try:
        from aqt.tikz_cache import TikzBulkRenderer, scan_collection_for_tikz

        specs = scan_collection_for_tikz(
            mw.col,
            normalize=normalize_tikz_source,
            key_for=_tikz_cache_key,
            script_source=tikzjax_script_source,
        )
        if not specs:
            print("[tikz-cache] scan: 0 tikz blocks")
            return
        missing = {h: src for h, src in specs.items() if not cache.has(h)}
        print(
            f"[tikz-cache] scan: {len(specs)} total, {len(missing)} missing"
        )
        if not missing:
            return
        media = getattr(mw.col, "media", None)
        have = getattr(media, "have", None) if media is not None else None
        if not callable(have):
            return
        if not (
            have(VENDORED_TIKZJAX_FILENAME) and have(VENDORED_TIKZJAX_FONTS_FILENAME)
        ):
            return
        if _bulk_renderer is None:
            _bulk_renderer = TikzBulkRenderer(
                mw=mw,
                cache=cache,
                tikzjax_filename=VENDORED_TIKZJAX_FILENAME,
                fonts_filename=VENDORED_TIKZJAX_FONTS_FILENAME,
            )
        print(f"[tikz-cache] enqueueing {len(missing)} items")
        _bulk_renderer.enqueue(missing)
        print(f"[tikz-cache] enqueue done; pending={_bulk_renderer.pending}")
    except Exception as exc:
        import traceback
        print(f"[tikz-cache] start failed: {exc!r}")
        traceback.print_exc()
        return


def _shutdown_bulk_render() -> None:
    global _bulk_renderer, _persistent_cache
    if _bulk_renderer is not None:
        try:
            _bulk_renderer.shutdown()
        except Exception:
            pass
        _bulk_renderer = None
    # Image cache files are written atomically on each add(); no flush.
    _persistent_cache = None


def setup_hook() -> None:
    """Register the card_will_show transformer and post-show JS runner.

    Idempotent — safe to call more than once.
    """
    if transform_card_html not in gui_hooks.card_will_show._hooks:  # type: ignore[attr-defined]
        gui_hooks.card_will_show.append(transform_card_html)
    if (
        _install_tikzjax_assets_for_collection
        not in gui_hooks.collection_did_load._hooks
    ):  # type: ignore[attr-defined]
        gui_hooks.collection_did_load.append(_install_tikzjax_assets_for_collection)
    if _run_in_reviewer not in gui_hooks.reviewer_did_show_question._hooks:  # type: ignore[attr-defined]
        gui_hooks.reviewer_did_show_question.append(_run_in_reviewer)
    if _run_in_reviewer not in gui_hooks.reviewer_did_show_answer._hooks:  # type: ignore[attr-defined]
        gui_hooks.reviewer_did_show_answer.append(_run_in_reviewer)
    if preload_upcoming_diagrams not in gui_hooks.reviewer_did_show_question._hooks:  # type: ignore[attr-defined]
        gui_hooks.reviewer_did_show_question.append(preload_upcoming_diagrams)
    if _start_bulk_render not in gui_hooks.collection_did_load._hooks:  # type: ignore[attr-defined]
        gui_hooks.collection_did_load.append(_start_bulk_render)
    if _shutdown_bulk_render not in gui_hooks.profile_will_close._hooks:  # type: ignore[attr-defined]
        gui_hooks.profile_will_close.append(_shutdown_bulk_render)
    if _handle_webview_cache_message not in gui_hooks.webview_did_receive_js_message._hooks:  # type: ignore[attr-defined]
        gui_hooks.webview_did_receive_js_message.append(_handle_webview_cache_message)
