#!/usr/bin/env python3
"""Build a debug-signed ARM64 APK with the complete Cinque v3 model.

Uses official SDK command-line tools directly; no Gradle or global installs.
The debug key persists in ignored project cache and is never regenerated over
an existing key. Its random password is supplied to signers through a file.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import zipfile

from fetch_android_sdk import fetch_tools
from fetch_kotlin import fetch_kotlin

ROOT = Path(__file__).resolve().parents[2]
SOURCE_SHA256 = "404a18cfd86d29637d20c697dfde245bb47c666ae016730ab674c65f4d1e1aa4"
VERSION_CODE = 7
VERSION_NAME = "0.1.6"
HOST_LIBRARIES = ("libonnxruntime.so", "libonnxruntime_providers_qnn.so", "libQnnHtp.so",
                  "libQnnHtpPrepare.so", "libQnnHtpV81Stub.so", "libQnnSystem.so", "libc++_shared.so")


def sha256_file(path):
    result = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def verify_jni_bytecode(java_home, classes, output, env):
    """Check the Kotlin/JVM ABI against the native bridge before making an APK."""
    package = "com.example.openpilotinference.android.NativeBridge"
    expected_native = {
        "createRun": "()J",
        "setTransport": "(JI)V",
        "run": "(JLjava/lang/String;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;Lcom/example/openpilotinference/android/NativeBridge$Callback;)V",
        "requestStop": "(J)V",
        "releaseRun": "(J)V",
        "setPreviewEnabled": "(Z)V",
        "renderPreview": "([B[I)V",
    }
    expected_callback = {
        "onState": "(Ljava/lang/String;Ljava/lang/String;I)V", "onStats": "(ZJD)V",
        "onPreview": "([BJJJJ)V", "onPerformance": "([D[J)V",
    }
    reports = []
    for name, expected, is_native in ((package, expected_native, True),
                                      (package + "$Callback", expected_callback, False)):
        listing = subprocess.check_output([str(java_home / "bin/javap"), "-classpath", str(classes),
                                           "-p", "-s", name], env=env, text=True)
        reports.append(listing)
        methods = {}
        for declaration, method, descriptor in re.findall(
                r"([^\n]*\b([\w$]+)\([^\n]*\);)\s+descriptor:\s+(\S+)", listing):
            methods[method] = (declaration, descriptor)
        for method, descriptor in expected.items():
            if method not in methods or methods[method][1] != descriptor:
                raise RuntimeError(f"JNI bytecode mismatch for {name}.{method}: expected {descriptor}")
            declaration = methods[method][0].split()
            if is_native and not {"static", "native"}.issubset(declaration):
                raise RuntimeError(f"{name}.{method} must remain static native (@JvmStatic external)")
            if not is_native and "static" in declaration:
                raise RuntimeError(f"JNI callback {name}.{method} must be an instance method")
        if is_native:
            actual_native = {method for method, (declaration, _) in methods.items() if "native" in declaration.split()}
            if actual_native != set(expected):
                raise RuntimeError("Unexpected/mangled NativeBridge native method names")
    (output / "jni-abi.txt").write_text("\n".join(reports))
    print("Verified Kotlin static native methods and JNI callback descriptors", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=ROOT / ".cache/android-models/cinque3/model.onnx")
    parser.add_argument("--deps", type=Path, default=ROOT / ".cache/android-deps")
    parser.add_argument("--tools", type=Path, default=ROOT / ".cache/android-apk-tools")
    parser.add_argument("--output", type=Path, default=ROOT / ".cache/android-apk")
    parser.add_argument("--reuse-jni", type=Path, help="Reuse an explicitly hashed deployed JNI library for a model-only release")
    parser.add_argument("--reuse-jni-sha256", help="Required SHA256 for --reuse-jni")
    args = parser.parse_args()
    if bool(args.reuse_jni) != bool(args.reuse_jni_sha256):
        parser.error("--reuse-jni and --reuse-jni-sha256 must be supplied together")
    if args.reuse_jni and sha256_file(args.reuse_jni) != args.reuse_jni_sha256:
        parser.error("Reused JNI library hash mismatch")
    manifest_file = args.model.parent / "manifest.json"
    if not args.model.is_file() or not manifest_file.is_file():
        parser.error("Prepared Cinque v3 model/manifest missing; run android/tools/prepare_model.py first")
    manifest = json.loads(manifest_file.read_text())
    if (manifest.get("model_id") != "cinque-v3-big" or
            manifest.get("source_sha256") != SOURCE_SHA256 or
            manifest.get("model_file") != args.model.name or
            manifest.get("deployment_sha256") != sha256_file(args.model)):
        parser.error("Cinque v3 model does not match its pinned deployment manifest")
    print("Verified full Cinque v3 model SHA256", flush=True)
    tools = fetch_tools(args.tools)
    kotlin = fetch_kotlin(args.tools)
    java_home = Path(tools["java_home"])
    build_tools = Path(tools["build_tools"])
    android_jar = Path(tools["sdk_root"]) / "platforms/android-35/android.jar"
    env = os.environ.copy()
    env["JAVA_HOME"] = str(java_home)
    env["PATH"] = str(java_home / "bin") + os.pathsep + env.get("PATH", "")
    def run(command):
        subprocess.run([str(value) for value in command], check=True, env=env)
    run([sys.executable, ROOT / "android/scripts/fetch_runtime.py", "--output", args.deps])
    ndk = Path(os.environ.get("ANDROID_NDK_HOME", os.environ.get("ANDROID_NDK_ROOT",
                                                                 args.deps / "android-ndk-r29")))
    if not (ndk / "build/cmake/android.toolchain.cmake").is_file():
        parser.error("Android NDK missing; set ANDROID_NDK_HOME to NDK r29 or later")
    args.output.mkdir(parents=True, exist_ok=True)
    native = args.output / "native"
    run(["cmake", "-S", ROOT / "android", "-B", native,
         "-DCMAKE_TOOLCHAIN_FILE=" + str(ndk / "build/cmake/android.toolchain.cmake"),
         "-DANDROID_ABI=arm64-v8a", "-DANDROID_PLATFORM=android-31", "-DANDROID_STL=c++_shared",
         "-DCMAKE_BUILD_TYPE=Release", "-DBUILD_TESTING=OFF", "-DOPIF_BUILD_SERVER=OFF",
         "-DOPIF_BUILD_JNI=ON", "-DORT_ROOT=" + str(args.deps.resolve())])
    run(["cmake", "--build", native, "--parallel", os.environ.get("CMAKE_BUILD_PARALLEL_LEVEL", "4")])
    stl = next(ndk.glob("toolchains/llvm/prebuilt/*/sysroot/usr/lib/aarch64-linux-android/libc++_shared.so"), None)
    if stl is None:
        parser.error("NDK ARM64 libc++_shared.so missing")
    shutil.copy2(stl, args.deps / "lib/libc++_shared.so")
    libraries = [args.deps / "lib" / name for name in HOST_LIBRARIES]
    if args.reuse_jni:
        shutil.copy2(args.reuse_jni, native / "libopif_jni.so")
    libraries += [args.deps / "dsp/libQnnHtpV81Skel.so", native / "libopif_jni.so"]
    for path in libraries:
        if not path.is_file():
            parser.error("Missing APK native library: " + str(path))

    source = ROOT / "android/app/src/main"
    generated, classes, dex = (args.output / name for name in ("generated", "classes", "dex"))
    for path in (generated, classes, dex):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir()
    resource_apk = args.output / "resources.apk"
    link = [build_tools / "aapt2", "link", "-I", android_jar,
            "--manifest", source / "AndroidManifest.xml", "--java", generated,
            "--min-sdk-version", "31", "--target-sdk-version", "35",
            "--version-code", str(VERSION_CODE), "--version-name", VERSION_NAME, "-o", resource_apk]
    if (source / "res").is_dir():
        compiled = args.output / "resources.zip"
        run([build_tools / "aapt2", "compile", "--dir", source / "res", "-o", compiled])
        link += [compiled]
    if (source / "assets").is_dir():
        link += ["-A", source / "assets"]
    run(link)
    if list((source / "java").rglob("*.java")):
        parser.error("Android app sources must be Kotlin under src/main/kotlin; only generated R.java uses javac")
    resource_sources = sorted(generated.rglob("*.java"))
    if resource_sources:
        run([java_home / "bin/javac", "--release", "8", "-encoding", "UTF-8",
             "-classpath", android_jar, "-d", classes, *resource_sources])
    sources = sorted((source / "kotlin").rglob("*.kt"))
    if not sources:
        parser.error("No Android Kotlin sources found")
    kotlin_classpath = os.pathsep.join(map(str, (android_jar, classes, kotlin["stdlib"], kotlin["annotations"])))
    run([kotlin["compiler"], "-jvm-target", "1.8", "-no-stdlib", "-no-reflect",
         "-classpath", kotlin_classpath, "-d", classes, *sources])
    verify_jni_bytecode(java_home, classes, args.output, env)
    classes_jar = args.output / "classes.jar"
    with zipfile.ZipFile(classes_jar, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(classes.rglob("*.class")):
            archive.write(path, path.relative_to(classes).as_posix())
    d8_command = [java_home / "bin/java", "-Xmx2g", "-cp", kotlin["d8_jar"], "com.android.tools.r8.D8",
                  "--min-api", "31", "--lib", android_jar, "--output", dex,
                  classes_jar, kotlin["stdlib"], kotlin["annotations"]]
    d8_log = args.output / "d8.log"
    with d8_log.open("w") as log:
        d8_result = subprocess.run([str(value) for value in d8_command], env=env, stdout=log,
                                   stderr=subprocess.STDOUT)
    diagnostics = d8_log.read_text()
    if diagnostics:
        print(diagnostics[-8000:], end="")
        if len(diagnostics) > 8000:
            print("Full D8 diagnostics: " + str(d8_log))
    if d8_result.returncode or "malformed kotlin.Metadata" in diagnostics or "error occurred when parsing kotlin metadata" in diagnostics:
        raise RuntimeError("D8 compilation/metadata validation failed; see " + str(d8_log))
    print("Compiled DEX with compatible D8 " + kotlin["d8_version"], flush=True)
    unsigned = args.output / "unsigned.apk"
    shutil.copyfile(resource_apk, unsigned)
    with zipfile.ZipFile(unsigned, "a", allowZip64=False) as archive:
        for path in sorted(dex.glob("*.dex")):
            archive.write(path, path.name, compress_type=zipfile.ZIP_DEFLATED)
        for path in libraries:
            archive.write(path, "lib/arm64-v8a/" + path.name, compress_type=zipfile.ZIP_STORED)
        # Avoid copying 731 MiB into a temporary asset tree or recompressing it
        # on every build; Android AssetManager can stream this stored entry.
        archive.write(args.model, "assets/models/model.onnx", compress_type=zipfile.ZIP_STORED)
        archive.write(manifest_file, "assets/models/manifest.json", compress_type=zipfile.ZIP_DEFLATED)
    aligned = args.output / "aligned.apk"
    run([build_tools / "zipalign", "-f", "-P", "16", "4", unsigned, aligned])
    key = args.tools / "debug.keystore"
    password = args.tools / "debug-key.password"
    # Keep development signing material untracked even with an output override.
    if key.resolve().is_relative_to(ROOT.resolve()):
        subprocess.run(["git", "check-ignore", "--quiet", str(key)], cwd=ROOT, check=True)
        subprocess.run(["git", "check-ignore", "--quiet", str(password)], cwd=ROOT, check=True)
    if key.exists() != password.exists():
        parser.error("Incomplete cached signing identity; restore its missing key/password file")
    if not key.exists():
        with os.fdopen(os.open(password, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "w") as out:
            out.write(secrets.token_hex(32) + "\n")
        old_umask = os.umask(0o077)
        try:
            run([java_home / "bin/keytool", "-genkeypair", "-noprompt", "-storetype", "PKCS12",
                 "-keystore", key, "-storepass:file", password, "-keypass:file", password,
                 "-alias", "androiddebugkey", "-keyalg", "RSA", "-keysize", "2048", "-validity", "10000",
                 "-dname", "CN=OpenPilotInference Debug,O=Android,C=US"])
        except Exception:
            # An interrupted key creation must not silently replace an identity.
            raise RuntimeError("Debug key generation failed; cached password retained for recovery")
        finally:
            os.umask(old_umask)
    key.chmod(0o600)
    password.chmod(0o600)
    apk = args.output / "OpenPilotInference-debug.apk"
    run([build_tools / "apksigner", "sign", "--ks", key, "--ks-key-alias", "androiddebugkey",
         "--ks-pass", "file:" + str(password),
         "--v1-signing-enabled", "false", "--v2-signing-enabled", "true", "--v3-signing-enabled", "true",
         "--out", apk, aligned])
    run([build_tools / "apksigner", "verify", "--verbose", apk])
    run([build_tools / "zipalign", "-c", "-P", "16", "4", apk])
    with zipfile.ZipFile(apk) as archive:
        names = set(archive.namelist())
        required = {"AndroidManifest.xml", "classes.dex", "assets/models/model.onnx",
                    "assets/models/manifest.json", *["lib/arm64-v8a/" + path.name for path in libraries]}
        if not required <= names:
            raise RuntimeError("APK missing packaged content: " + str(required - names))
        if any("libQnnCpu" in name or "libQnnGpu" in name for name in names):
            raise RuntimeError("APK unexpectedly contains a CPU/GPU QNN backend")
        packed_digest = hashlib.sha256()
        with archive.open("assets/models/model.onnx") as model_stream:
            for block in iter(lambda: model_stream.read(1024 * 1024), b""):
                packed_digest.update(block)
        if packed_digest.hexdigest() != manifest["deployment_sha256"]:
            raise RuntimeError("Packaged model hash mismatch")
    report = {"apk": str(apk.resolve()), "apk_sha256": sha256_file(apk), "apk_bytes": apk.stat().st_size,
              "package": "com.example.openpilotinference.android", "min_sdk": 31, "target_sdk": 35,
              "version_code": VERSION_CODE, "version_name": VERSION_NAME,
              "model_sha256": manifest["deployment_sha256"], "native_libraries": [path.name for path in libraries],
              "attention_mask": ("shared_fp16_add_bias" if any(c.get("pass") == "additive-mask" for c in manifest.get("changes", {}).get("fusion_candidates", [])) else manifest.get("changes", {}).get("attention_mask_bias", {}).get("mode", "original_where")),
              "reused_jni_sha256": args.reuse_jni_sha256,
              "graph_optimizations": manifest.get("changes", {}).get("fusion_candidates", []),
              "app_language": "Kotlin", "kotlin_version": kotlin["version"], "jni_abi_verified": True,
              "d8_version": kotlin["d8_version"],
              "kotlin_runtime_jars": [Path(kotlin[key]).name for key in ("stdlib", "annotations")],
              "signature_verified": True, "zip_alignment_verified": True, "device_run_verified": False}
    (args.output / "build-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Built and verified APK: " + str(apk.resolve()), flush=True)


if __name__ == "__main__":
    main()
