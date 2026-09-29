#!/usr/bin/env python3
"""Compile the actual Kotlin chart code; exercise only host-side statistics/math."""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / '.cache/android-apk-tools'
java_homes = list((TOOLS / 'jdk').glob('*/Contents/Home'))
if not java_homes:
    raise SystemExit('Cached Android build JDK is required; run the normal build tool setup first.')
java_home = java_homes[0]
android_jar = TOOLS / 'sdk/platforms/android-35/android.jar'
kotlin = TOOLS / 'kotlin'
env = dict(os.environ, JAVA_HOME=str(java_home))
with tempfile.TemporaryDirectory(prefix='opif-performance-check-') as directory:
    work = Path(directory)
    stub = work / 'Process.java'
    stub.write_text('package android.os; public class Process { '
                    'public static final int THREAD_PRIORITY_BACKGROUND = 10; '
                    'public static void setThreadPriority(int priority) {} }\n')
    classes = work / 'classes'
    classes.mkdir()
    subprocess.run([str(java_home / 'bin/javac'), '-d', str(classes), str(stub)], check=True)
    source = ROOT / 'android/app/src/main/kotlin/com/example/openpilotinference/android/PerformanceHistory.kt'
    test = ROOT / 'android/tests/performance_history_check.kt'
    subprocess.run([str(kotlin / 'bin/kotlinc'), '-jvm-target', '1.8', '-classpath', str(android_jar),
                    str(source), str(test), '-d', str(classes)], env=env, check=True)
    runtime = os.pathsep.join(map(str, [classes, kotlin / 'lib/kotlin-stdlib.jar', android_jar]))
    subprocess.run([str(java_home / 'bin/java'), '-cp', runtime,
                    'com.example.openpilotinference.android.Performance_history_checkKt'], check=True)
