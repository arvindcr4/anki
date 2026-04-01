# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import json
import sys
from typing import Any

import pip_system_certs.wrapt_requests
import requests

pip_system_certs.wrapt_requests.inject_truststore()


def fetch_versions() -> list[str]:
    """Fetch and return all versions from PyPI, sorted by upload time."""
    response = requests.get("https://pypi.org/pypi/aqt/json", timeout=30)
    response.raise_for_status()
    data: dict[str, Any] = response.json()

    releases = data.get("releases", {})
    version_times = sorted(
        (
            (version, files[0].get("upload_time_iso_8601"))
            for version, files in releases.items()
            if files and files[0].get("upload_time_iso_8601")
        ),
        key=lambda item: item[1],
    )
    return [version for version, _ in version_times]


def main():
    try:
        print(json.dumps(fetch_versions()))
    except (requests.RequestException, ValueError, TypeError) as e:
        print(f"Error fetching versions: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
