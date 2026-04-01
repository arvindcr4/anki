# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import subprocess
import sys
from pathlib import Path

# If no arguments provided, build for the anki_mac_helper package
if len(sys.argv) == 1:
    script_dir = Path(__file__).parent
    out_dylib = script_dir / "anki_mac_helper" / "libankihelper.dylib"
    src_files = list(script_dir.glob("*.swift"))
else:
    out_dylib, *src_files = map(Path, sys.argv[1:])

out_dir = out_dylib.parent.resolve()
src_dir = src_files[0].parent.resolve()

# Build for both architectures
architectures = ["arm64", "x86_64"]
temp_files = []

# Ensure output directory exists
out_dir.mkdir(parents=True, exist_ok=True)

try:
    for arch in architectures:
        target = f"{arch}-apple-macos11"
        temp_out = out_dir / f"temp_{arch}.dylib"
        temp_files.append(temp_out)

        args = [
            "swiftc",
            "-target",
            target,
            "-emit-library",
            "-module-name",
            "ankihelper",
            "-O",
            *src_files,
            "-o",
            str(temp_out),
        ]
        subprocess.run(args, check=True, cwd=out_dir)

    # Create universal binary
    lipo_args = ["lipo", "-create", "-output", str(out_dylib), *map(str, temp_files)]
    subprocess.run(lipo_args, check=True)
finally:
    for temp_file in temp_files:
        temp_file.unlink(missing_ok=True)
