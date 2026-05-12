#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import contextlib
import datetime as dt
import hashlib
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse


APP_NAME = "Anki TikZ.app"
BUNDLE_ID = "net.ankiweb.dtop.tikz.local"
LABEL = "net.ankiweb.tikz.updater"
EXIT_INSTALLED = 20
DEFAULT_MANIFEST_URL = (
    "https://github.com/arvindcr4/anki/releases/latest/download/"
    "anki-tikz-appcast.json"
)
SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "AnkiTikZ"
LOG_FILE = Path.home() / "Library" / "Logs" / "AnkiTikZUpdater.log"


class UpdateError(RuntimeError):
    pass


def default_config() -> dict:
    return {
        "app_path": f"/Applications/{APP_NAME}",
        "channel": "stable",
        "manifest_url": DEFAULT_MANIFEST_URL,
        "check_interval_seconds": 14_400,
        "support_dir": str(SUPPORT_DIR),
        "log_file": str(LOG_FILE),
        "public_key_path": str(SUPPORT_DIR / "update-public-key.pem"),
        "require_signature": False,
        "allow_insecure_http": False,
        "run_pid_file": str(SUPPORT_DIR / "run.pid"),
    }


def log(message: str, config: dict | None = None) -> None:
    target = Path((config or {}).get("log_file") or LOG_FILE)
    target.parent.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with target.open("a", encoding="utf-8") as fh:
        fh.write(f"[{stamp}] {message}\n")


def notify(message: str) -> None:
    script = f"display notification {json.dumps(message)} with title \"Anki TikZ\""
    subprocess.run(
        ["/usr/bin/osascript", "-e", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")
    tmp.replace(path)


def load_config(path: Path | None) -> dict:
    config = default_config()
    if path and path.exists():
        config.update(read_json(path))
    return config


def config_path_from_args(path: str | None) -> Path:
    return Path(path).expanduser() if path else SUPPORT_DIR / "updater.json"


def install_agent(args: argparse.Namespace) -> int:
    config_path = config_path_from_args(args.config)
    config = load_config(config_path)
    support_dir = Path(config.get("support_dir") or SUPPORT_DIR).expanduser()
    support_dir.mkdir(parents=True, exist_ok=True)

    updater_dest = support_dir / "anki_tikz_updater.py"
    source_updater = Path(args.source_updater or __file__).expanduser()
    if source_updater.resolve() != updater_dest.resolve():
        shutil.copy2(source_updater, updater_dest)
    updater_dest.chmod(0o755)

    if args.public_key:
        public_key_source = Path(args.public_key).expanduser()
        public_key_dest = support_dir / "update-public-key.pem"
        shutil.copy2(public_key_source, public_key_dest)
        config["public_key_path"] = str(public_key_dest)
        config["require_signature"] = True

    config["app_path"] = str(Path(args.app_path).expanduser())
    config["manifest_url"] = args.manifest_url or config.get("manifest_url") or ""
    config["channel"] = args.channel or config.get("channel") or "stable"
    config["require_signature"] = bool(args.require_signature) or bool(
        config.get("require_signature")
    )
    config["support_dir"] = str(support_dir)
    config["log_file"] = str(Path(config.get("log_file") or LOG_FILE).expanduser())
    config["run_pid_file"] = str(support_dir / "run.pid")
    write_json(config_path, config)

    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    launch_agent = {
        "Label": LABEL,
        "ProgramArguments": [
            "/usr/bin/python3",
            str(updater_dest),
            "check",
            "--config",
            str(config_path),
            "--install-if-idle",
        ],
        "RunAtLoad": True,
        "StartInterval": int(config.get("check_interval_seconds") or 14_400),
        "ProcessType": "Background",
        "StandardOutPath": config["log_file"],
        "StandardErrorPath": config["log_file"],
    }
    new_plist = plistlib.dumps(launch_agent)
    if not plist_path.exists() or plist_path.read_bytes() != new_plist:
        plist_path.write_bytes(new_plist)

    uid = os.getuid()
    domain = f"gui/{uid}"
    subprocess.run(
        ["/bin/launchctl", "bootout", domain, str(plist_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    boot = subprocess.run(
        ["/bin/launchctl", "bootstrap", domain, str(plist_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if boot.returncode != 0:
        log(f"launch agent bootstrap skipped/failed: {boot.stderr.strip()}", config)
    subprocess.run(
        ["/bin/launchctl", "kickstart", "-k", f"{domain}/{LABEL}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    log(f"installed launch agent at {plist_path}", config)
    return 0


def read_bundle_version(app_path: Path) -> str:
    info_plist = app_path / "Contents" / "Info.plist"
    if not info_plist.exists():
        return "0"
    with info_plist.open("rb") as fh:
        info = plistlib.load(fh)
    return str(info.get("CFBundleVersion") or info.get("CFBundleShortVersionString") or "0")


def version_key(value: object) -> tuple:
    parts: list[tuple[int, object]] = []
    for token in re.findall(r"\d+|[A-Za-z]+", str(value or "")):
        if token.isdigit():
            parts.append((0, int(token)))
        else:
            parts.append((1, token.lower()))
    return tuple(parts)


def is_newer(update: dict, current_version: str) -> bool:
    candidate = update.get("build") or update.get("version")
    if not candidate:
        return False
    if str(candidate) == current_version:
        return False
    return version_key(candidate) > version_key(current_version)


def open_url(url: str, timeout: int = 30):
    request = urllib.request.Request(url, headers={"User-Agent": "AnkiTikZUpdater/1.0"})
    return urllib.request.urlopen(request, timeout=timeout)


def require_safe_url(url: str, config: dict) -> None:
    parsed = urlparse(url)
    if parsed.scheme == "file":
        return
    if parsed.scheme != "https" and not config.get("allow_insecure_http"):
        raise UpdateError(f"refusing non-HTTPS update URL: {url}")


def fetch_manifest(config: dict) -> dict:
    url = str(config.get("manifest_url") or "")
    if not url:
        raise UpdateError("manifest URL is empty")
    require_safe_url(url, config)
    log(f"checking manifest {url}", config)
    with open_url(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def candidate_updates(manifest: dict, channel: str) -> list[dict]:
    raw_updates = manifest.get("updates") or manifest.get("items") or [manifest]
    updates: list[dict] = []
    for item in raw_updates:
        item_channel = item.get("channel", "stable")
        platform = item.get("platform") or item.get("os") or "macos"
        if item_channel not in (channel, "all"):
            continue
        if platform not in ("macos", "darwin", "macos-universal", "all"):
            continue
        updates.append(item)
    return sorted(
        updates,
        key=lambda item: version_key(item.get("build") or item.get("version")),
        reverse=True,
    )


def normalize_artifact(update: dict) -> dict:
    artifact = dict(update.get("artifact") or {})
    for key in ("url", "sha256", "size", "signature", "signature_url"):
        if key in update and key not in artifact:
            artifact[key] = update[key]
    if not artifact.get("url"):
        raise UpdateError("update manifest does not include an artifact URL")
    if not artifact.get("sha256"):
        raise UpdateError("update manifest does not include artifact.sha256")
    return artifact


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_artifact(artifact: dict, config: dict, dest: Path) -> None:
    url = str(artifact["url"])
    require_safe_url(url, config)
    log(f"downloading {url}", config)
    if url.startswith("file://"):
        shutil.copy2(urllib.request.url2pathname(urlparse(url).path), dest)
    else:
        with open_url(url, timeout=120) as response, dest.open("wb") as fh:
            shutil.copyfileobj(response, fh, length=1024 * 1024)
    expected = str(artifact["sha256"]).lower()
    actual = sha256_file(dest)
    if actual != expected:
        raise UpdateError(f"sha256 mismatch: expected {expected}, got {actual}")
    if artifact.get("size") and int(artifact["size"]) != dest.stat().st_size:
        raise UpdateError("downloaded artifact size does not match manifest")


def signature_bytes(artifact: dict, config: dict) -> bytes | None:
    if artifact.get("signature"):
        return base64.b64decode(str(artifact["signature"]), validate=True)
    if artifact.get("signature_url"):
        url = str(artifact["signature_url"])
        require_safe_url(url, config)
        with open_url(url, timeout=30) as response:
            return response.read()
    return None


def verify_signature(artifact: dict, archive: Path, config: dict) -> None:
    public_key = Path(str(config.get("public_key_path") or "")).expanduser()
    require_signature = bool(config.get("require_signature"))
    if not public_key.exists():
        if require_signature:
            raise UpdateError(f"required update public key missing: {public_key}")
        log("signature verification skipped: no public key configured", config)
        return

    sig = signature_bytes(artifact, config)
    if not sig:
        if require_signature:
            raise UpdateError("required update signature is missing from manifest")
        log("signature verification skipped: manifest has no signature", config)
        return

    with tempfile.NamedTemporaryFile(delete=False) as sig_file:
        sig_file.write(sig)
        sig_path = Path(sig_file.name)
    try:
        result = subprocess.run(
            [
                "/usr/bin/openssl",
                "dgst",
                "-sha256",
                "-verify",
                str(public_key),
                "-signature",
                str(sig_path),
                str(archive),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise UpdateError(f"signature verification failed: {result.stderr.strip()}")
        log("signature verification passed", config)
    finally:
        with contextlib.suppress(FileNotFoundError):
            sig_path.unlink()


def extract_archive(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    if archive.suffix.lower() != ".zip":
        raise UpdateError("only .zip app archives are supported")
    if shutil.which("ditto"):
        subprocess.run(
            ["/usr/bin/ditto", "-x", "-k", str(archive), str(destination)],
            check=True,
        )
    else:
        import zipfile

        with zipfile.ZipFile(archive) as zf:
            zf.extractall(destination)


def find_app_bundle(root: Path) -> Path:
    preferred = list(root.rglob(APP_NAME))
    if preferred:
        return preferred[0]
    apps = list(root.rglob("*.app"))
    if not apps:
        raise UpdateError("downloaded archive did not contain an app bundle")
    return apps[0]


def validate_app_bundle(app_path: Path) -> None:
    info_plist = app_path / "Contents" / "Info.plist"
    if not info_plist.exists():
        raise UpdateError(f"{app_path} is missing Contents/Info.plist")
    with info_plist.open("rb") as fh:
        info = plistlib.load(fh)
    bundle_id = info.get("CFBundleIdentifier")
    if bundle_id != BUNDLE_ID:
        raise UpdateError(f"unexpected bundle id {bundle_id!r}")
    executable = info.get("CFBundleExecutable")
    if not executable:
        raise UpdateError("bundle does not declare CFBundleExecutable")
    executable_path = app_path / "Contents" / "MacOS" / str(executable)
    if not os.access(executable_path, os.X_OK):
        raise UpdateError(f"bundle executable is not executable: {executable_path}")


def stage_app(app_path: Path, update: dict, config: dict) -> None:
    support_dir = Path(config.get("support_dir") or SUPPORT_DIR).expanduser()
    staged_dir = support_dir / "staged"
    tmp_app = staged_dir / f"{APP_NAME}.tmp"
    final_app = staged_dir / APP_NAME
    shutil.rmtree(tmp_app, ignore_errors=True)
    shutil.rmtree(final_app, ignore_errors=True)
    staged_dir.mkdir(parents=True, exist_ok=True)
    if shutil.which("ditto"):
        subprocess.run(["/usr/bin/ditto", str(app_path), str(tmp_app)], check=True)
    else:
        shutil.copytree(app_path, tmp_app, symlinks=True)
    tmp_app.rename(final_app)
    write_json(staged_dir / "manifest.json", update)
    log(f"staged update {update.get('version')} at {final_app}", config)


def pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def pid_command(pid: int) -> str:
    result = subprocess.run(
        ["/bin/ps", "-p", str(pid), "-o", "command="],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    return result.stdout.strip()


def app_is_running(config: dict) -> bool:
    pid_file = Path(str(config.get("run_pid_file") or SUPPORT_DIR / "run.pid"))
    if not pid_file.exists():
        return False
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except ValueError:
        pid_file.unlink(missing_ok=True)
        return False
    if not pid_is_running(pid):
        pid_file.unlink(missing_ok=True)
        return False
    command = pid_command(pid)
    if "tools/run.py" in command or "AnkiTikZ" in command or "Anki TikZ" in command:
        return True
    pid_file.unlink(missing_ok=True)
    return False


def remove_quarantine(app_path: Path) -> None:
    subprocess.run(
        ["/usr/bin/xattr", "-dr", "com.apple.quarantine", str(app_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def cleanup_backups(backup_dir: Path, keep: int = 2) -> None:
    backups = sorted(backup_dir.glob("Anki TikZ-*.app"))
    for old in backups[:-keep]:
        shutil.rmtree(old, ignore_errors=True)


def install_staged(args: argparse.Namespace, config: dict) -> int:
    app_path = Path(args.app_path or config.get("app_path") or f"/Applications/{APP_NAME}")
    support_dir = Path(config.get("support_dir") or SUPPORT_DIR).expanduser()
    staged_app = support_dir / "staged" / APP_NAME
    if not staged_app.exists():
        return 0
    if not args.force and app_is_running(config):
        log("staged update waiting: app is still running", config)
        return 0

    validate_app_bundle(staged_app)
    backup_dir = support_dir / "previous"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_app = backup_dir / f"Anki TikZ-{dt.datetime.now():%Y%m%d%H%M%S}.app"
    log(f"installing staged update to {app_path}", config)
    try:
        if app_path.exists():
            shutil.move(str(app_path), str(backup_app))
        shutil.move(str(staged_app), str(app_path))
        remove_quarantine(app_path)
        cleanup_backups(backup_dir)
        log("staged update installed", config)
        notify("Update installed.")
        return EXIT_INSTALLED
    except Exception:
        if backup_app.exists() and not app_path.exists():
            with contextlib.suppress(Exception):
                shutil.move(str(backup_app), str(app_path))
        raise


def skip_for_frequency(config: dict, max_frequency: int | None) -> bool:
    if not max_frequency:
        return False
    support_dir = Path(config.get("support_dir") or SUPPORT_DIR).expanduser()
    last_check = support_dir / "last-check"
    if not last_check.exists():
        return False
    try:
        last = float(last_check.read_text(encoding="utf-8"))
    except ValueError:
        return False
    return time.time() - last < max_frequency


def mark_checked(config: dict) -> None:
    support_dir = Path(config.get("support_dir") or SUPPORT_DIR).expanduser()
    support_dir.mkdir(parents=True, exist_ok=True)
    (support_dir / "last-check").write_text(str(time.time()), encoding="utf-8")


def run_check(args: argparse.Namespace, config: dict) -> int:
    if skip_for_frequency(config, args.max_frequency):
        return 0
    mark_checked(config)
    manifest = fetch_manifest(config)
    updates = candidate_updates(manifest, str(config.get("channel") or "stable"))
    if not updates:
        log("no update candidate for configured channel/platform", config)
        return 0

    current_version = read_bundle_version(Path(str(config.get("app_path"))))
    update = next((item for item in updates if is_newer(item, current_version)), None)
    if not update:
        log(f"already up to date at {current_version}", config)
        return 0

    artifact = normalize_artifact(update)
    with tempfile.TemporaryDirectory(prefix="anki-tikz-update-") as tmp:
        tmpdir = Path(tmp)
        archive = tmpdir / "update.zip"
        download_artifact(artifact, config, archive)
        verify_signature(artifact, archive, config)
        extracted = tmpdir / "extracted"
        extract_archive(archive, extracted)
        app = find_app_bundle(extracted)
        validate_app_bundle(app)
        stage_app(app, update, config)

    notify("Update downloaded. It will install when Anki TikZ is closed.")
    if args.install_if_idle:
        return install_staged(
            argparse.Namespace(app_path=config.get("app_path"), force=False), config
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Anki TikZ background updater")
    subparsers = parser.add_subparsers(dest="command", required=True)

    agent = subparsers.add_parser("install-agent")
    agent.add_argument("--app-path", required=True)
    agent.add_argument("--manifest-url", default=DEFAULT_MANIFEST_URL)
    agent.add_argument("--channel", default="stable")
    agent.add_argument("--config")
    agent.add_argument("--source-updater")
    agent.add_argument("--public-key")
    agent.add_argument("--require-signature", action="store_true")

    check = subparsers.add_parser("check")
    check.add_argument("--config")
    check.add_argument("--install-if-idle", action="store_true")
    check.add_argument("--max-frequency", type=int)

    staged = subparsers.add_parser("install-staged")
    staged.add_argument("--config")
    staged.add_argument("--app-path")
    staged.add_argument("--force", action="store_true")

    args = parser.parse_args()
    if args.command == "install-agent":
        return install_agent(args)

    config = load_config(config_path_from_args(getattr(args, "config", None)))
    try:
        if args.command == "check":
            return run_check(args, config)
        if args.command == "install-staged":
            return install_staged(args, config)
    except Exception as exc:
        log(f"{args.command} failed: {exc}", config)
        return 0 if args.command == "check" else 1
    raise AssertionError(args.command)


if __name__ == "__main__":
    sys.exit(main())
