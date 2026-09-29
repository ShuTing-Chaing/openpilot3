#!/usr/bin/env python3
"""Push cached artifacts incrementally and run the NPU server over adb."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[2]
SOURCE_SHA256 = "404a18cfd86d29637d20c697dfde245bb47c666ae016730ab674c65f4d1e1aa4"
HOST_LIBRARIES = ("libonnxruntime.so", "libonnxruntime_providers_qnn.so", "libQnnHtp.so",
                  "libQnnHtpPrepare.so", "libQnnHtpV81Stub.so", "libQnnSystem.so", "libc++_shared.so")
DSP_LIBRARY = "libQnnHtpV81Skel.so"


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", default=os.environ.get("ANDROID_SERIAL"))
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--deps", type=Path, default=ROOT / ".cache/android-deps")
    parser.add_argument("--binary", type=Path, default=ROOT / ".cache/android-build/opif-server")
    parser.add_argument("--remote-dir", default="/data/local/tmp/opif")
    parser.add_argument("--port", type=int, default=5555)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--benchmark", type=int)
    parser.add_argument("--benchmark-input", type=Path)
    parser.add_argument("--benchmark-output", help="Device output filename, under remote-dir")
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--verbose", action="store_true", help="Record detailed ORT/QNN node validation logs")
    args = parser.parse_args()
    if not args.remote_dir.startswith("/data/local/tmp/") or ".." in Path(args.remote_dir).parts:
        parser.error("--remote-dir must be a directory under /data/local/tmp/")
    if not 1 <= args.port <= 65535:
        parser.error("--port must be 1..65535")
    if args.benchmark is not None and not 1 <= args.benchmark <= 1000000:
        parser.error("--benchmark must be 1..1000000")
    if ((args.benchmark is not None) != (args.benchmark_input is not None) or
            (args.benchmark_output and args.benchmark is None) or
            (args.validate_only and args.benchmark is not None)):
        parser.error("Use --benchmark N with --benchmark-input, separately from --validate-only")
    if args.benchmark_output and Path(args.benchmark_output).name != args.benchmark_output:
        parser.error("--benchmark-output must be a filename")
    manifest_path = args.model.parent / "manifest.json"
    required = [args.model, manifest_path, args.binary, args.deps / "dsp" / DSP_LIBRARY]
    required += [args.deps / "lib" / name for name in HOST_LIBRARIES]
    if args.benchmark_input:
        required.append(args.benchmark_input)
    for path in required:
        if not path.is_file():
            parser.error(f"Missing artifact: {path}; prepare models and build first")
    if args.benchmark_input and (args.benchmark_input.stat().st_size == 0 or
                                args.benchmark_input.stat().st_size % 393216):
        parser.error("--benchmark-input must contain complete 393216-byte packed6 frames")
    manifest = json.loads(manifest_path.read_text())
    if (manifest.get("model_id") != "cinque-v3-big" or
            manifest.get("source_sha256") != SOURCE_SHA256 or
            manifest.get("model_file") != args.model.name or
            manifest.get("deployment_sha256") != sha256_file(args.model)):
        parser.error("Model does not match the pinned Cinque v3 deployment manifest; prepare models again")
    print("Verified pinned Cinque v3 model and deployment SHA256", flush=True)
    adb = ["adb"] + (["-s", args.serial] if args.serial else [])
    def shell(command):
        subprocess.run(adb + ["shell", command], check=True)
    def push(source, target):
        subprocess.run(adb + ["push", "--sync", str(source), target], check=True)
    soc = subprocess.check_output(adb + ["shell", "getprop", "ro.soc.model"], text=True).strip()
    if not soc.upper().startswith("SM8850"):
        parser.error(f"Expected Snapdragon 8 Elite Gen 5 / SM8850; device reports {soc!r}")
    remote = args.remote_dir.rstrip("/")
    shell("mkdir -p " + " ".join(shlex.quote(remote + suffix) for suffix in ("", "/lib", "/dsp", "/models", "/profiles")))
    push(args.binary, remote + "/opif-server")
    for name in HOST_LIBRARIES:
        push(args.deps / "lib" / name, remote + "/lib/" + name)
    push(args.deps / "dsp" / DSP_LIBRARY, remote + "/dsp/" + DSP_LIBRARY)
    push(args.model, remote + "/models/" + args.model.name)
    push(manifest_path, remote + "/models/manifest.json")
    shell("chmod 755 " + shlex.quote(remote + "/opif-server"))
    command = [remote + "/opif-server", "--model", remote + "/models/" + args.model.name,
               "--qnn-library", remote + "/lib/libonnxruntime_providers_qnn.so",
               "--backend", remote + "/lib/libQnnHtp.so", "--port", str(args.port)]
    if args.validate_only:
        command.append("--validate-only")
    if args.benchmark is not None:
        command += ["--benchmark", str(args.benchmark)]
    if args.benchmark_input:
        push(args.benchmark_input, remote + "/benchmark_input.bin")
        command += ["--benchmark-input", remote + "/benchmark_input.bin"]
    if args.benchmark_output:
        command += ["--benchmark-output", remote + "/" + args.benchmark_output]
    if args.profile:
        command += ["--profile", remote + "/profiles/qnn"]
    if args.verbose:
        command.append("--verbose")
    # Keep platform libraries in the system linker namespace. Prepending all
    # vendor libraries can select inaccessible vendor copies of system libs.
    environment = {"LD_LIBRARY_PATH": remote + "/lib",
                   "ADSP_LIBRARY_PATH": remote + "/dsp;/vendor/lib/rfsa/adsp;/vendor/dsp/cdsp;/vendor/dsp;/system/lib/rfsa/adsp"}
    prefix = " ".join(key + "=" + shlex.quote(value) for key, value in environment.items())
    # Record this invocation's exact PID. On Ctrl-C, stop only the matching
    # executable, allowing the server to flush its ORT profile on SIGTERM.
    pid_file = remote + "/server-" + uuid.uuid4().hex + ".pid"
    quoted_pid = shlex.quote(pid_file)
    launch = ("cd " + shlex.quote(remote) + " && echo $$ > " + quoted_pid +
              " && exec env " + prefix + " " + shlex.join(command))
    try:
        shell(launch)
    except KeyboardInterrupt:
        stop = ("pid=$(cat " + quoted_pid + " 2>/dev/null); "
                "case $pid in ''|*[!0-9]*) ;; *) "
                "if [ \"$(readlink /proc/$pid/exe 2>/dev/null)\" = " +
                shlex.quote(remote + "/opif-server") + " ]; then kill -TERM \"$pid\"; fi ;; esac")
        print("Stopping this server with SIGTERM", flush=True)
        shell(stop)
    finally:
        shell("rm -f " + quoted_pid)


if __name__ == "__main__":
    main()
