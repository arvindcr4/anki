# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Persistent on-disk TikZ image cache + background bulk renderer.

Three pieces:

1. ``TikzImageCache`` — a directory of ``<hash>.svg`` files inside the
   user's profile folder. Each rendered TikZ block becomes one SVG file
   that the media server can serve as an image. Survives restarts.

2. ``scan_collection_for_tikz(col, ...)`` — walks every note in the
   collection, pulls every ``[tikz]…[/tikz]`` block out of the fields,
   returns ``{hash: render_body}`` ready for the renderer to grind through.

3. ``TikzBulkRenderer`` — a hidden ``QWebEngineView`` that loads TikZJax
   once and then processes the queue, writing each completed SVG straight
   to disk via the cache. Throttled so the user's session isn't
   disturbed; bails on individual renders that hang past the timeout.

The cache is purely an optimisation: when ``_wrap_tikz`` sees a hash whose
SVG file already exists, it inlines the SVG into the card so it renders
instantly. A live TikZJax compile still happens on miss.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from typing import TYPE_CHECKING, Any

from anki.collection import Collection
from aqt.qt import QTimer

if TYPE_CHECKING:
    from aqt.main import AnkiQt


_TIKZ_RE = re.compile(r"\[tikz\](.+?)\[/tikz\]", re.DOTALL | re.IGNORECASE)


_CACHE_DIRNAME = "tikz-cache"
# Path component on the media server used to serve cached SVGs.
TIKZ_CACHE_URL_PREFIX = "_tikz_cache"


def cache_url_for(key: str) -> str:
    """Return the URL the webview should fetch this cached SVG from."""
    return f"/{TIKZ_CACHE_URL_PREFIX}/{key}.svg"


class TikzImageCache:
    """A directory of ``<hash>.svg`` files served by the media server.

    Thread-safe via an internal lock. Writes are atomic (``tmp → rename``)
    so a partial write never produces a half-broken SVG. An in-memory set
    of known hashes makes ``has()`` cheap to call from the card-render
    hot path.
    """

    def __init__(self, profile_folder: str) -> None:
        self._dir = os.path.join(profile_folder, _CACHE_DIRNAME)
        self._lock = threading.Lock()
        self._known: set[str] = set()
        self._ensure_dir()
        self._rescan()

    def _ensure_dir(self) -> None:
        try:
            os.makedirs(self._dir, exist_ok=True)
        except OSError:
            pass

    def _rescan(self) -> None:
        try:
            entries = os.listdir(self._dir)
        except OSError:
            return
        for name in entries:
            if not name.endswith(".svg"):
                continue
            stem = name[:-4]
            if stem:
                self._known.add(stem)

    @property
    def directory(self) -> str:
        return self._dir

    def path_for(self, key: str) -> str:
        return os.path.join(self._dir, f"{key}.svg")

    def has(self, key: str) -> bool:
        with self._lock:
            if key in self._known:
                return True
        # Fall back to filesystem check in case the in-memory set drifts.
        if os.path.exists(self.path_for(key)):
            with self._lock:
                self._known.add(key)
            return True
        return False

    def get(self, key: str) -> str | None:
        """Return a cached SVG string, or ``None`` when unavailable.

        Cache hits are embedded directly into the reviewer HTML instead of
        fetched as ``<img>`` resources. That avoids broken image placeholders
        when a webview is on a transient media-server origin or an image load
        races with cache creation.
        """
        if not self.has(key):
            return None
        try:
            with open(self.path_for(key), encoding="utf-8") as f:
                svg = f.read()
        except OSError:
            with self._lock:
                self._known.discard(key)
            return None
        if "<svg" not in svg:
            return None
        return svg

    def add(self, key: str, svg: str) -> bool:
        if not key or not svg or "<svg" not in svg:
            return False
        with self._lock:
            if key in self._known:
                return False
        path = self.path_for(key)
        tmp_path = path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(svg)
            os.replace(tmp_path, path)
        except OSError:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            return False
        with self._lock:
            self._known.add(key)
        return True

    def remove(self, key: str) -> None:
        try:
            os.remove(self.path_for(key))
        except OSError:
            pass
        with self._lock:
            self._known.discard(key)


# --------------------------------------------------------------------- scan


def scan_collection_for_tikz(
    col: Collection, normalize: Any, key_for: Any, script_source: Any
) -> dict[str, str]:
    """Walk every note's fields and pull out unique tikz render bodies.

    ``normalize``, ``key_for`` and ``script_source`` are passed in from
    ``aqt.diagrams`` to avoid a circular import; they correspond to
    ``normalize_tikz_source``, ``_tikz_cache_key`` and
    ``tikzjax_script_source``.
    """
    specs: dict[str, str] = {}
    try:
        rows = col.db.list("select flds from notes")
    except Exception:
        return specs
    for flds in rows:
        if not flds or "[tikz]" not in flds.lower():
            continue
        for match in _TIKZ_RE.finditer(flds):
            try:
                body = normalize(match.group(1))
                render_body = script_source(body)
                key = key_for(render_body)
            except Exception:
                continue
            if key and key not in specs:
                specs[key] = render_body
    return specs


# ----------------------------------------------------- background renderer


_HIDDEN_RENDERER_HTML = """<!doctype html>
<html><head>
<meta charset="utf-8">
<link rel="stylesheet" href="%(fonts_url)s">
<script src="%(tikzjax_url)s"></script>
</head>
<body style="margin:0;padding:0;background:transparent;">
<div id="stage"></div>
<script>
// Bridge sanity probe — pycmd should be available by DocumentReady.
(function () {
  function probe(label) {
    if (typeof pycmd === 'function') {
      try { pycmd('anki-tikz-bulk-dbg:probe-' + label); } catch (e) {}
    }
    console.log('[tikz-probe] ' + label + ' pycmd=' + (typeof pycmd));
  }
  probe('immediate');
  document.addEventListener('DOMContentLoaded', function () { probe('domready'); });
  window.addEventListener('load', function () { probe('load'); });
})();
window._ankiBulkReady = false;
function _waitReady(cb) {
  if (typeof window.process_tikz === 'function') { cb(); return; }
  window.setTimeout(function () { _waitReady(cb); }, 200);
}
function _ankiDbg(msg) {
  if (typeof pycmd === 'function') {
    try { pycmd('anki-tikz-bulk-dbg:' + msg); } catch (e) {}
  }
}
window._ankiBulkRender = function (hash, source) {
  _ankiDbg('start ' + hash);
  const stage = document.getElementById('stage');
  // Wipe ALL prior render artifacts — TikZJax sometimes inserts SVGs
  // outside the immediate script parent, so just rebuild from scratch.
  stage.innerHTML = '';
  const wrap = document.createElement('div');
  wrap.setAttribute('data-h', hash);
  const script = document.createElement('script');
  script.type = 'text/tikz';
  script.text = source;
  wrap.appendChild(script);
  stage.appendChild(wrap);
  _waitReady(function () {
    _ankiDbg('ready ' + hash);
    try {
      const result = window.process_tikz();
      _ankiDbg('called ' + hash + ' isPromise=' + !!(result && result.then));
      const finish = function () {
        // SVG may end up inside wrap, inside stage, or as a sibling of
        // the script — search the broadest scope.
        const svg = stage.querySelector('svg') || document.querySelector('#stage svg');
        _ankiDbg('finish ' + hash + ' svg=' + !!svg);
        if (svg && typeof pycmd === 'function') {
          pycmd('anki-tikz-bulk:' + JSON.stringify({h: hash, s: svg.outerHTML}));
        } else if (typeof pycmd === 'function') {
          pycmd('anki-tikz-bulk-fail:' + hash);
        }
      };
      if (result && typeof result.then === 'function') {
        result.then(finish).catch(function (e) {
          _ankiDbg('reject ' + hash);
          if (typeof pycmd === 'function') pycmd('anki-tikz-bulk-fail:' + hash);
        });
      } else {
        window.setTimeout(finish, 500);
      }
    } catch (e) {
      _ankiDbg('throw ' + hash);
      if (typeof pycmd === 'function') pycmd('anki-tikz-bulk-fail:' + hash);
    }
  });
};
_waitReady(function () {
  window._ankiBulkReady = true;
  if (typeof pycmd === 'function') pycmd('anki-tikz-bulk-ready');
});
</script>
</body></html>
"""


class TikzBulkRenderer:
    """Owns a hidden webview that grinds through queued TikZ sources.

    The renderer is created lazily on first ``enqueue`` so we don't pay the
    QWebEngineView construction cost when there's nothing to do (e.g. the
    user's collection has zero TikZ).
    """

    def __init__(
        self,
        mw: AnkiQt,
        cache: TikzImageCache,
        tikzjax_filename: str,
        fonts_filename: str,
        on_progress: Any = None,
    ) -> None:
        self._mw = mw
        self._cache = cache
        self._tikzjax_filename = tikzjax_filename
        self._fonts_filename = fonts_filename
        self._queue: list[tuple[str, str]] = []
        self._in_flight: tuple[str, str] | None = None
        self._ready = False
        self._view: Any = None
        self._render_started_at: float = 0.0
        self._on_progress = on_progress
        self._render_timeout_ms = 15000
        self._gap_ms = 250
        self._timeout_timer: QTimer | None = None

    def enqueue(self, specs: dict[str, str]) -> None:
        """Add missing specs to the work queue."""
        added = False
        in_queue = {h for h, _ in self._queue}
        if self._in_flight is not None:
            in_queue.add(self._in_flight[0])
        for key, source in specs.items():
            if self._cache.has(key):
                continue
            if key in in_queue:
                continue
            self._queue.append((key, source))
            in_queue.add(key)
            added = True
        if added and self._view is None:
            self._spawn_view()
        elif added and self._ready and self._in_flight is None:
            self._pump()

    def _spawn_view(self) -> None:
        print("[tikz-cache] _spawn_view entered")
        from aqt.qt import QUrl
        from aqt.webview import AnkiWebView, AnkiWebViewKind

        try:
            view = AnkiWebView(parent=None, kind=AnkiWebViewKind.DEFAULT)
        except TypeError:
            view = AnkiWebView()
        print("[tikz-cache] AnkiWebView created")
        view.set_open_links_externally(True)
        view.allow_drops = False
        view.requiresCol = False
        view.set_bridge_command(self._on_bridge, self)
        # QtWebEngine suspends pages that are never realised on screen, so
        # the bridge script never fires DOMContentLoaded and our pycmd
        # probes go silent. Show the view off-screen with size > 0 to keep
        # the renderer active without it being visible to the user.
        view.resize(640, 480)
        try:
            from aqt.qt import Qt

            view.setWindowFlags(
                Qt.WindowType.Tool
                | Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnBottomHint
            )
            view.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            view.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        except Exception:
            pass
        view.show()
        try:
            view.move(-20000, -20000)
        except Exception:
            pass
        self._view = view
        html = _HIDDEN_RENDERER_HTML % {
            "fonts_url": f"/{self._fonts_filename}",
            "tikzjax_url": f"/{self._tikzjax_filename}",
        }
        server_url = self._mw.serverURL().rstrip("/")
        from aqt.mediasrv import PageContext

        webview_id = id(view)
        self._mw.mediaServer.set_page_html(webview_id, html, PageContext.UNKNOWN)
        url = f"{server_url}/_anki/legacyPageData?id={webview_id}"
        print(f"[tikz-cache] spawning hidden view {webview_id} → {url}")
        view.load_url(QUrl(url))

    def _on_bridge(self, cmd: str) -> Any:
        print(f"[tikz-cache] bridge: {cmd[:120]}")
        if cmd.startswith("anki-tikz-bulk-dbg:"):
            return None
        if cmd == "anki-tikz-bulk-ready":
            self._ready = True
            self._pump()
            return None
        if cmd.startswith("anki-tikz-bulk-fail:"):
            self._finish(cmd.split(":", 1)[1], None)
            return None
        if cmd.startswith("anki-tikz-bulk:"):
            payload = cmd.split(":", 1)[1]
            try:
                obj = json.loads(payload)
            except json.JSONDecodeError:
                return None
            key = obj.get("h")
            svg = obj.get("s")
            if isinstance(key, str) and isinstance(svg, str):
                self._cache.add(key, svg)
                self._finish(key, svg)
            return None
        return None

    def _finish(self, key: str, svg: str | None) -> None:
        timed_out = False
        if self._timeout_timer is not None:
            try:
                if self._timeout_timer.isActive():
                    self._timeout_timer.stop()
                else:
                    # If the timer is no longer active when we get here, it
                    # already fired — i.e. the render hung past the budget.
                    timed_out = svg is None
            except Exception:
                pass
            self._timeout_timer = None
        if self._in_flight is not None and self._in_flight[0] == key:
            self._in_flight = None
        if callable(self._on_progress):
            try:
                self._on_progress(key, svg)
            except Exception:
                pass
        # If LaTeX wedged the wasm, the renderer process is now stuck and
        # subsequent eval()s will queue forever. Reload the page to reset.
        if timed_out:
            self._reload_view_then_pump()
        else:
            QTimer.singleShot(self._gap_ms, self._pump)

    def _reload_view_then_pump(self) -> None:
        if self._view is None:
            return
        self._ready = False
        try:
            self._view.reload()
        except Exception:
            pass
        # ``_on_bridge`` will flip ``_ready`` back when the reloaded page
        # pycmds ``anki-tikz-bulk-ready``; that handler already pumps.

    def _pump(self) -> None:
        if not self._ready or self._view is None:
            return
        if self._in_flight is not None:
            return
        if not self._queue:
            return
        key, source = self._queue.pop(0)
        if self._cache.has(key):
            QTimer.singleShot(0, self._pump)
            return
        self._in_flight = (key, source)
        self._render_started_at = time.monotonic()
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(lambda k=key: self._finish(k, None))
        timer.start(self._render_timeout_ms)
        self._timeout_timer = timer
        safe_source = json.dumps(source)
        safe_key = json.dumps(key)
        self._view.eval(
            f"window._ankiBulkRender({safe_key}, {safe_source});"
        )

    @property
    def pending(self) -> int:
        return len(self._queue) + (1 if self._in_flight is not None else 0)

    def shutdown(self) -> None:
        if self._timeout_timer is not None:
            try:
                self._timeout_timer.stop()
            except Exception:
                pass
            self._timeout_timer = None
        if self._view is not None:
            try:
                self._view.cleanup()
            except Exception:
                pass
            try:
                self._view.deleteLater()
            except Exception:
                pass
            self._view = None
        self._ready = False
        self._in_flight = None
        self._queue = []
