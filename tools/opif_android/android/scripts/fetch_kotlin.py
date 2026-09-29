#!/usr/bin/env python3
"""Fetch pinned official Kotlin/JVM and compatible D8; keep compiler jars off device."""
import argparse
import json
from pathlib import Path

from fetch_android_sdk import ROOT, download, unpack_zip

VERSION = "2.4.20"
COMPILER_SHA256 = "59e9ca74c7904ef2c122b12114937673ccce68de820a663f0ed66ccf8799e0b7"
D8_VERSION = "9.1.43"
D8_SHA256 = "1a855e13fbcbc5fd9c019a56b88fc687c29be9a5efd35b6d60b791e892d46e23"


def fetch_kotlin(output):
    downloads = output / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    archive = downloads / f"kotlin-compiler-{VERSION}.zip"
    download(f"https://github.com/JetBrains/kotlin/releases/download/v{VERSION}/" + archive.name,
             archive, COMPILER_SHA256, "sha256")
    home = output / "kotlin"
    marker = home / "version.json"
    if not marker.is_file() or json.loads(marker.read_text()).get("version") != VERSION:
        unpack_zip(archive, home)
        marker.write_text(json.dumps({"version": VERSION, "compiler_sha256": COMPILER_SHA256}, indent=2) + "\n")
    paths = {"version": VERSION, "compiler": str((home / "bin/kotlinc").resolve()),
             "stdlib": str((home / "lib/kotlin-stdlib.jar").resolve()),
             "annotations": str((home / "lib/annotations-13.0.jar").resolve())}
    for key in ("compiler", "stdlib", "annotations"):
        if not Path(paths[key]).is_file():
            raise RuntimeError("Kotlin distribution missing " + paths[key])
    # https://developer.android.com/build/kotlin-support requires R8/D8 >=
    # 9.1.29 for Kotlin 2.4. SDK 35's bundled D8 8.6 cannot parse its metadata.
    d8 = downloads / f"r8-{D8_VERSION}.jar"
    download(f"https://dl.google.com/dl/android/maven2/com/android/tools/r8/{D8_VERSION}/{d8.name}",
             d8, D8_SHA256, "sha256")
    paths.update(d8_jar=str(d8.resolve()), d8_version=D8_VERSION)
    return paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".cache/android-apk-tools")
    args = parser.parse_args()
    print(json.dumps(fetch_kotlin(args.output), indent=2))


if __name__ == "__main__":
    main()
