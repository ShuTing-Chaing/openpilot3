#!/usr/bin/env python3
"""Fetch verified official ARM64 ORT/QNN artifacts into the project cache.

Only HTP V81 libraries are staged; no QNN CPU or GPU backend is included.
Versions are the combination documented by Qualcomm for QNN EP 2.6.0.
"""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = (
    ("com/microsoft/onnxruntime/onnxruntime-android", "1.27.0",
     "077dec5e2d821234c7dc0aba584bec8f999854b546c754cab93a90741c56fbeb"),
    ("com/qualcomm/qti/onnxruntime-android-qnn", "2.6.0",
     "169add91932e27196e0ab704f53fe8cd517af3ecee0d4a73fbf14513ab4551a6"),
    ("com/qualcomm/qti/qnn-runtime", "2.50.0",
     "b507656e4031d8aa6a7ab0fecf725b941096737ad7440ad7ea288f7c9cc9d743"),
)
HOST_LIBS = {
    "libonnxruntime.so", "libonnxruntime_providers_qnn.so", "libQnnHtp.so",
    "libQnnHtpPrepare.so", "libQnnHtpV81Stub.so", "libQnnSystem.so",
}


def digest(path):
    with path.open("rb") as stream:
        value = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
        return value.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".cache/android-deps")
    args = parser.parse_args()
    for directory in ("downloads", "include", "lib", "dsp"):
        (args.output / directory).mkdir(parents=True, exist_ok=True)
    manifest = {"ort": "1.27.0", "qnn_ep": "2.6.0", "qnn_runtime": "2.50.0",
                "soc_model": 87, "htp_arch": 81, "files": {}}
    for package, version, expected in ARTIFACTS:
        name = f"{package.rsplit('/', 1)[1]}-{version}.aar"
        archive = args.output / "downloads" / name
        if not archive.exists() or digest(archive) != expected:
            url = f"https://repo.maven.apache.org/maven2/{package}/{version}/{name}"
            partial = archive.with_suffix(".aar.download")
            print(f"Downloading {name}", flush=True)
            urllib.request.urlretrieve(url, partial)
            if digest(partial) != expected:
                partial.unlink()
                raise RuntimeError(f"SHA256 mismatch for {name}")
            partial.replace(archive)
        with zipfile.ZipFile(archive) as source:
            for member in source.infolist():
                path = Path(member.filename)
                if member.filename.startswith("headers/") and path.suffix == ".h":
                    destination = args.output / "include" / path.name
                elif member.filename.startswith("jni/arm64-v8a/") and path.name in HOST_LIBS:
                    destination = args.output / "lib" / path.name
                elif member.filename == "jni/arm64-v8a/libQnnHtpV81Skel.so":
                    destination = args.output / "dsp" / path.name
                else:
                    continue
                content = source.read(member)
                if not destination.exists() or destination.read_bytes() != content:
                    destination.write_bytes(content)
                manifest["files"][str(destination.relative_to(args.output))] = hashlib.sha256(content).hexdigest()
        print(f"Verified {name}", flush=True)
    (args.output / "runtime-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"ARM64 / HTP V81 runtime ready: {args.output}")


if __name__ == "__main__":
    main()
