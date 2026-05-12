# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import os
import plistlib
import re
import subprocess
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aqt
from anki.buildinfo import buildhash
from anki.collection import CheckForUpdateResponse, Collection
from anki.utils import dev_mode, int_time, int_version, plat_desc
from aqt.operations import QueryOp
from aqt.package import (
    launcher_executable as _launcher_executable,
)
from aqt.package import (
    update_and_restart as _update_and_restart,
)
from aqt.qt import *
from aqt.utils import openLink, show_warning, showText, tooltip, tr

SPARKLE_NS = "{http://www.andymatuschak.org/xml-namespaces/sparkle}"


@dataclass(frozen=True)
class TikzUpdateInfo:
    current_version: str | None
    latest_version: str
    latest_short_version: str | None
    latest_title: str | None
    feed_url: str

    @property
    def display_version(self) -> str:
        return self.latest_short_version or self.latest_version


def sparkle_app_bundle() -> Path | None:
    if bundle := os.environ.get("ANKI_TIKZ_APP_BUNDLE"):
        bundle_path = Path(bundle)
        if bundle_path.is_dir():
            return bundle_path

    if runner := sparkle_update_runner():
        runner_path = Path(runner)
        if len(runner_path.parents) >= 4:
            return runner_path.parents[3]

    bundle_path = Path("/Applications/Anki TikZ.app")
    if bundle_path.is_dir():
        return bundle_path

    return None


def sparkle_update_runner() -> str | None:
    if runner := os.environ.get("ANKI_TIKZ_SPARKLE_RUNNER"):
        if Path(runner).is_file():
            return runner

    if bundle := os.environ.get("ANKI_TIKZ_APP_BUNDLE"):
        runner_path = Path(bundle) / "Contents/Library/Sparkle/run-sparkle-update"
        if runner_path.is_file():
            return str(runner_path)

    runner_path = Path(
        "/Applications/Anki TikZ.app/Contents/Library/Sparkle/run-sparkle-update"
    )
    if runner_path.is_file():
        return str(runner_path)

    return None


def _sparkle_feed_url() -> str | None:
    if feed_url := os.environ.get("ANKI_TIKZ_SPARKLE_FEED_URL"):
        return feed_url

    if bundle := sparkle_app_bundle():
        info_path = bundle / "Contents/Info.plist"
        if info_path.is_file():
            with info_path.open("rb") as file:
                info = plistlib.load(file)
            if feed_url := info.get("SUFeedURL"):
                return str(feed_url)

    return None


def _current_tikz_version() -> str | None:
    if bundle := sparkle_app_bundle():
        info_path = bundle / "Contents/Info.plist"
        if info_path.is_file():
            with info_path.open("rb") as file:
                info = plistlib.load(file)
            version = info.get("CFBundleVersion") or info.get("CFBundleShortVersionString")
            if version:
                return str(version)

    return None


def _version_numbers(version: str) -> list[int]:
    return [int(match) for match in re.findall(r"\d+", version)]


def _version_is_newer(candidate: str, current: str | None) -> bool:
    if not current:
        return True

    candidate_numbers = _version_numbers(candidate)
    current_numbers = _version_numbers(current)
    if candidate_numbers and current_numbers:
        max_len = max(len(candidate_numbers), len(current_numbers))
        candidate_numbers.extend([0] * (max_len - len(candidate_numbers)))
        current_numbers.extend([0] * (max_len - len(current_numbers)))
        return candidate_numbers > current_numbers

    return candidate > current


def _fetch_latest_tikz_update() -> TikzUpdateInfo:
    feed_url = _sparkle_feed_url()
    if not feed_url:
        raise RuntimeError("No Sparkle update feed URL is configured.")

    request = urllib.request.Request(
        feed_url,
        headers={"User-Agent": "Anki TikZ"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            appcast = response.read(2 * 1024 * 1024)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"Update feed returned HTTP {exc.code}: {exc.reason}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach update feed: {exc.reason}") from exc

    try:
        root = ET.fromstring(appcast)
    except ET.ParseError as exc:
        raise RuntimeError(f"Update feed is not valid XML: {exc}") from exc

    item = root.find("./channel/item")
    if item is None:
        raise RuntimeError("Update feed does not contain any releases.")

    enclosure = item.find("enclosure")
    latest_version = (
        item.findtext(f"{SPARKLE_NS}version")
        or (enclosure.get(f"{SPARKLE_NS}version") if enclosure is not None else None)
    )
    if not latest_version:
        raise RuntimeError("Latest release is missing a Sparkle version.")

    latest_short_version = (
        item.findtext(f"{SPARKLE_NS}shortVersionString")
        or (
            enclosure.get(f"{SPARKLE_NS}shortVersionString")
            if enclosure is not None
            else None
        )
    )

    return TikzUpdateInfo(
        current_version=_current_tikz_version(),
        latest_version=latest_version,
        latest_short_version=latest_short_version,
        latest_title=item.findtext("title"),
        feed_url=feed_url,
    )


def _ask_to_download_tikz_update(mw: aqt.AnkiQt, info: TikzUpdateInfo) -> bool:
    msgbox = QMessageBox(mw)
    msgbox.setWindowTitle("Anki TikZ Update")
    msgbox.setIcon(QMessageBox.Icon.Information)
    msgbox.setText(f"Update found: Anki TikZ {info.display_version}.")
    current = info.current_version or "unknown"
    msgbox.setInformativeText(
        f"Current version: {current}\n\n"
        f"Do you want to download version {info.display_version} now?"
    )
    msgbox.setStandardButtons(
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    msgbox.setDefaultButton(QMessageBox.StandardButton.Yes)
    return msgbox.exec() == QMessageBox.StandardButton.Yes


def _show_tikz_is_current(mw: aqt.AnkiQt, current_version: str | None) -> None:
    suffix = f"\n\nCurrent version: {current_version}" if current_version else ""
    QMessageBox.information(
        mw,
        "Anki TikZ Update",
        f"Anki TikZ is already up to date.{suffix}",
    )


def _run_sparkle_update(
    mw: aqt.AnkiQt,
    runner: str,
    version: str | None = None,
) -> None:
    if version:
        tooltip(f"Downloading Anki TikZ {version}...")
    else:
        tooltip("Downloading Anki TikZ update...")

    def run_update() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                runner,
                "--check-immediately",
                "--interactive",
                "--allow-major-upgrades",
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

    def on_done(future: Any) -> None:
        try:
            result = future.result()
        except Exception as exc:
            show_warning(
                f"Could not start the Anki TikZ updater:\n\n{exc}",
                parent=mw,
            )
            return

        if result.returncode:
            detail = result.stdout.strip()
            msg = "Anki TikZ update download failed."
            if detail:
                msg += f"\n\n{detail}"
            show_warning(msg, parent=mw)
            return

        tooltip("Anki TikZ update download started.")

    mw.taskman.run_in_background(run_update, on_done, uses_collection=False)


def check_for_tikz_update() -> bool:
    runner = sparkle_update_runner()
    if not runner:
        return False

    from aqt import mw

    tooltip("Checking for Anki TikZ updates...")

    def run_check() -> TikzUpdateInfo:
        return _fetch_latest_tikz_update()

    def on_done(future: Any) -> None:
        try:
            info = future.result()
        except Exception as exc:
            show_warning(
                f"Could not check for Anki TikZ updates:\n\n{exc}",
                parent=mw,
            )
            return

        if not _version_is_newer(info.latest_version, info.current_version):
            _show_tikz_is_current(mw, info.current_version)
            return

        if _ask_to_download_tikz_update(mw, info):
            _run_sparkle_update(mw, runner, info.display_version)

    mw.taskman.run_in_background(run_check, on_done, uses_collection=False)
    return True


def check_for_update() -> None:
    from aqt import mw

    def do_check(_col: Collection) -> CheckForUpdateResponse:
        return mw.backend.check_for_update(
            version=int_version(),
            buildhash=buildhash,
            os=plat_desc(),
            install_id=mw.pm.meta["id"],
            last_message_id=max(0, mw.pm.meta["lastMsg"]),
        )

    def on_done(resp: CheckForUpdateResponse) -> None:
        # is clock off?
        if not dev_mode:
            diff = abs(resp.current_time - int_time())
            if diff > 300:
                diff_text = tr.qt_misc_second(count=diff)
                warn = (
                    tr.qt_misc_in_order_to_ensure_your_collection(val="%s") % diff_text
                )
                show_warning(
                    warn,
                    parent=mw,
                    textFormat=Qt.TextFormat.RichText,
                    callback=mw.app.closeAllWindows,
                )
                return
        # should we show a message?
        if msg := resp.message:
            showText(msg, parent=mw, type="html")
            mw.pm.meta["lastMsg"] = resp.last_message_id
        # has Anki been updated?
        if ver := resp.new_version:
            if mw.pm.meta.get("suppressUpdate", None) != ver:
                prompt_to_update(mw, ver)

    def on_fail(exc: Exception) -> None:
        print(f"update check failed: {exc}")

    QueryOp(parent=mw, op=do_check, success=on_done).failure(
        on_fail
    ).without_collection().run_in_background()


def prompt_to_update(mw: aqt.AnkiQt, ver: str) -> None:
    msg = (
        tr.qt_misc_anki_updatedanki_has_been_released(val=ver)
        + tr.qt_misc_would_you_like_to_download_it()
    )

    msgbox = QMessageBox(mw)
    msgbox.setStandardButtons(
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    msgbox.setIcon(QMessageBox.Icon.Information)
    msgbox.setText(msg)

    button = QPushButton(tr.qt_misc_ignore_this_update())
    msgbox.addButton(button, QMessageBox.ButtonRole.RejectRole)
    msgbox.setDefaultButton(QMessageBox.StandardButton.Yes)
    ret = msgbox.exec()

    if msgbox.clickedButton() == button:
        # ignore this update
        mw.pm.meta["suppressUpdate"] = ver
    elif ret == QMessageBox.StandardButton.Yes:
        if _launcher_executable():
            _update_and_restart()
        else:
            openLink(aqt.appWebsiteDownloadSection)
