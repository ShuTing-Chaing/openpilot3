#!/usr/bin/env python3
"""Fetch pinned official Android APK tools and Temurin JDK into project cache.

No global JDK, SDK, PATH, signing identity, or SDK installation is changed.
The Android checksums are from Google's repository2-3.xml; JDK SHA256 values
are from the official adoptium/temurin17-binaries release asset metadata.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import tarfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
PLATFORM_URL = "https://dl.google.com/android/repository/platform-35_r02.zip"
PLATFORM_SHA1 = "0bb560a90a7a2cbd0dd8348224d518b638fe7949"
BUILD_TOOLS = {
    "Darwin": ("macosx", "93ab8ce91230e067b5add4bfa79919c52b27f072"),
    "Linux": ("linux", "2cfaa0bbb2336e9ec18ed3ecea84fa2e2af607bc"),
}
JDK = {
    ("Darwin", "arm64"): ("aarch64_mac", "196d13ba5f10414bef7f6a05a9b3f00edacb18ebacef2b99485db9e2ee18f0e8"),
    ("Darwin", "x86_64"): ("x64_mac", "c01975da12ed4235250ff891fe8bba73a9e73037d444b269c9d0922b5dbc8e0a"),
    ("Linux", "x86_64"): ("x64_linux", "3808d1d15e3ec6bd5b84057fb5d84c33d8a1536a258146bcea2e603fc726e08e"),
}


def digest(path, algorithm="sha256"):
    value = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(data)
    return value.hexdigest()


def download(url, target, expected, algorithm):
    if target.is_file() and digest(target, algorithm) == expected:
        return
    print("Downloading " + target.name, flush=True)
    partial = target.with_name(target.name + ".download")
    request = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(request, timeout=60) as response:
        length = int(response.headers.get("Content-Length", "0"))
        ranges = response.headers.get("Accept-Ranges") == "bytes"
    if ranges and length > 8 * 1024 * 1024:
        # Google's large archives can be slow on a single connection. Bound
        # concurrency and write each verified-size range to its own file.
        part_dir = target.with_name(target.name + ".parts")
        part_dir.mkdir(exist_ok=True)
        spans = [(start, min(start + 4 * 1024 * 1024, length))
                 for start in range(0, length, 4 * 1024 * 1024)]
        def fetch(span):
            start, end = span
            path = part_dir / str(start)
            if path.is_file() and path.stat().st_size == end - start:
                return path
            req = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end - 1}"})
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(req, timeout=120) as response:
                        if response.status != 206:
                            raise RuntimeError("Server ignored HTTP Range")
                        data = response.read()
                    if len(data) != end - start:
                        raise RuntimeError("Truncated range download")
                    path.write_bytes(data)
                    return path
                except Exception:
                    if attempt == 2:
                        raise
        with ThreadPoolExecutor(max_workers=8) as workers:
            parts = list(workers.map(fetch, spans))
        with partial.open("wb") as output:
            for path in parts:
                with path.open("rb") as source:
                    shutil.copyfileobj(source, output)
    else:
        urllib.request.urlretrieve(url, partial)
    if digest(partial, algorithm) != expected:
        partial.unlink()
        raise RuntimeError("Checksum mismatch: " + target.name)
    partial.replace(target)
    print("Verified " + target.name, flush=True)


def unpack_zip(archive, target):
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as source:
        for entry in source.infolist():
            relative = Path(*Path(entry.filename).parts[1:])
            if relative == Path("."):
                continue
            if relative.is_absolute() or ".." in relative.parts:
                raise RuntimeError("Unsafe archive path")
            destination = target / relative
            if entry.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            mode = entry.external_attr >> 16
            data = source.read(entry)
            if stat.S_ISLNK(mode):
                link = data.decode()
                if not (destination.parent / link).resolve().is_relative_to(target.resolve()):
                    raise RuntimeError("Unsafe archive symlink")
                if not destination.is_symlink():
                    destination.symlink_to(link)
            else:
                destination.write_bytes(data)
                if mode:
                    destination.chmod(mode & 0o777)


def fetch_tools(output):
    host = (platform.system(), platform.machine())
    if host not in JDK:
        raise RuntimeError("APK tool bootstrap supports macOS ARM64/x64 and Linux x64")
    downloads = output / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    sdk = output / "sdk"
    platform_dir = sdk / "platforms/android-35"
    build_dir = sdk / "build-tools/35.0.0"
    platform_archive = downloads / "platform-35_r02.zip"
    download(PLATFORM_URL, platform_archive, PLATFORM_SHA1, "sha1")
    if not (platform_dir / "android.jar").is_file():
        unpack_zip(platform_archive, platform_dir)
    build_host, build_hash = BUILD_TOOLS[host[0]]
    build_name = f"build-tools_r35_{build_host}.zip"
    build_archive = downloads / build_name
    download("https://dl.google.com/android/repository/" + build_name,
             build_archive, build_hash, "sha1")
    if not (build_dir / "apksigner").is_file():
        unpack_zip(build_archive, build_dir)
    jdk_host, jdk_hash = JDK[host]
    jdk_name = f"OpenJDK17U-jdk_{jdk_host}_hotspot_17.0.20.1_1.tar.gz"
    jdk_archive = downloads / jdk_name
    download("https://github.com/adoptium/temurin17-binaries/releases/download/"
             "jdk-17.0.20.1%2B1/" + jdk_name, jdk_archive, jdk_hash, "sha256")
    jdk_dir = output / "jdk"
    home = jdk_dir / "jdk-17.0.20.1+1"
    if host[0] == "Darwin":
        home /= "Contents/Home"
    if not (home / "bin/javac").is_file():
        jdk_dir.mkdir(exist_ok=True)
        with tarfile.open(jdk_archive) as source:
            source.extractall(jdk_dir, filter="data")
    result = {"java_home": str(home.resolve()), "sdk_root": str(sdk.resolve()),
              "build_tools": str(build_dir.resolve()), "compile_sdk": 35,
              "jdk": "17.0.20.1+1", "build_tools_version": "35.0.0"}
    (output / "tools.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".cache/android-apk-tools")
    args = parser.parse_args()
    result = fetch_tools(args.output)
    print("Android APK tools ready: " + result["sdk_root"])


if __name__ == "__main__":
    main()
