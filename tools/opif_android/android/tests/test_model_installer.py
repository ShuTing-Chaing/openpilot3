"""Run the resource loader on a host JVM with bounded fake Android storage.

Set JSON_JAR to a host org.json jar and optionally JAVA/JAVAC to a JDK. The pinned
Kotlin compiler and standard library come from .cache/android-apk-tools/kotlin;
run android/scripts/fetch_android_sdk.py and android/scripts/fetch_kotlin.py first,
or use android/scripts/build_apk.sh to bootstrap both. No global Kotlin is used. The
app uses Android's builtin org.json and needs no added JSON dependency. Tests
exercise real filesystem copy, SHA-256, markers and cancellation; three small
Android stubs only supply resources, a private directory and available space.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ANDROID = Path(__file__).resolve().parents[1]
TOOLS = ANDROID.parent / ".cache/android-apk-tools"
STUBS = {
    "android/content/Context.java": r"""
package android.content;
import android.content.res.AssetManager;
import java.io.File;
public final class Context {
    private final File files;
    private final AssetManager assets;
    public Context(File files, AssetManager assets) { this.files = files; this.assets = assets; }
    public File getFilesDir() { return files; }
    public AssetManager getAssets() { return assets; }
}
""",
    "android/content/res/AssetManager.java": r"""
package android.content.res;
import java.io.*;
import java.util.*;
public final class AssetManager {
    public static final int ACCESS_STREAMING = 2;
    public final Map<String, byte[]> files = new HashMap<>();
    public long modelBytesRead;
    public int modelOpens;
    public InputStream open(String path, int mode) throws IOException {
        if (!files.containsKey(path)) throw new FileNotFoundException(path);
        boolean model = path.equals("models/model.onnx");
        if (model) modelOpens++;
        return new FilterInputStream(new ByteArrayInputStream(files.get(path))) {
            @Override public int read(byte[] bytes, int offset, int length) throws IOException {
                int count = in.read(bytes, offset, length);
                if (model && count > 0) modelBytesRead += count;
                return count;
            }
        };
    }
}
""",
    "android/os/StatFs.java": r"""
package android.os;
public final class StatFs {
    public static long available = Long.MAX_VALUE;
    public StatFs(String path) {}
    public long getAvailableBytes() { return available; }
}
""",
}
HARNESS = r"""
import android.content.Context;
import android.content.res.AssetManager;
import android.os.StatFs;
import com.example.openpilotinference.android.ModelInstaller;
import java.io.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import org.json.JSONObject;

public final class ModelInstallerHostTest {
    private static final String SOURCE = "404a18cfd86d29637d20c697dfde245bb47c666ae016730ab674c65f4d1e1aa4";
    private static final byte[] MODEL = new byte[2 * 1024 * 1024 + 17];
    private static String hash;
    private static int checks;

    private static void check(boolean value, String message) {
        checks++;
        if (!value) throw new AssertionError(message);
    }

    private static JSONObject manifest() throws Exception {
        JSONObject metadata = new JSONObject();
        metadata.put("openpilot.model_id", "cinque-v3-big");
        metadata.put("openpilot.source_sha256", SOURCE);
        metadata.put("openpilot.abi_version", "1");
        metadata.put("openpilot.precision", "fp16-original");
        metadata.put("openpilot.allow_cpu_fallback", "0");
        JSONObject result = new JSONObject();
        result.put("schema_version", 1);
        result.put("model_id", "cinque-v3-big");
        result.put("source_sha256", SOURCE);
        result.put("model_file", "model.onnx");
        result.put("precision", "fp16-original");
        result.put("quantized", false);
        result.put("host_state_updates", false);
        result.put("metadata", metadata);
        result.put("deployment_sha256", hash);
        result.put("deployment_bytes", MODEL.length);
        return result;
    }

    private static Context fixture(File base, String name, JSONObject manifest, byte[] model) throws Exception {
        File files = new File(base, name);
        check(files.mkdirs(), "cannot make test directory");
        AssetManager assets = new AssetManager();
        assets.files.put("models/manifest.json", manifest.toString().getBytes(StandardCharsets.UTF_8));
        if (model != null) assets.files.put("models/model.onnx", model);
        return new Context(files, assets);
    }

    private static void expectFailure(Context context, String message) throws Exception {
        List<Integer> progress = new ArrayList<>();
        try {
            ModelInstaller.prepare(context, progress::add, () -> false);
            throw new AssertionError("Expected failure: " + message);
        } catch (IOException expected) {
            check(!progress.contains(100), "failure signalled ready: " + message);
        }
        try (java.util.stream.Stream<Path> paths = Files.walk(context.getFilesDir().toPath())) {
            check(paths.noneMatch(p -> p.toString().endsWith(".partial")), "partial file survived: " + message);
        }
    }

    public static void main(String[] arguments) throws Exception {
        File base = new File(arguments[0]);
        for (int index = 0; index < MODEL.length; index++) MODEL[index] = (byte) (index * 17);
        StringBuilder hex = new StringBuilder();
        for (byte value : MessageDigest.getInstance("SHA-256").digest(MODEL))
            hex.append(String.format("%02x", value & 255));
        hash = hex.toString();

        Context context = fixture(base, "good", manifest(), MODEL);
        List<Integer> progress = new ArrayList<>();
        File installed = ModelInstaller.prepare(context, progress::add, () -> false);
        check(Arrays.equals(MODEL, Files.readAllBytes(installed.toPath())), "fresh model bytes differ");
        check(installed.getParentFile().getName().equals(hash), "deployment digest directory missing");
        check(progress.get(0) == 0 && progress.get(progress.size() - 1) == 100, "progress endpoints wrong");
        for (int index = 1; index < progress.size(); index++)
            check(progress.get(index) >= progress.get(index - 1), "progress moved backwards");
        File marker = new File(installed.getParentFile(), "verified.json");
        check(marker.isFile(), "verified marker absent");

        long bytesRead = context.getAssets().modelBytesRead;
        int opens = context.getAssets().modelOpens;
        check(ModelInstaller.prepare(context, null, null).equals(installed), "cache returned different model");
        check(context.getAssets().modelBytesRead == bytesRead, "cache unnecessarily read model asset");
        check(context.getAssets().modelOpens == opens + 1, "cache failed to confirm APK asset exists");
        context.getAssets().files.remove("models/model.onnx");
        expectFailure(context, "missing asset despite valid cache");
        context.getAssets().files.put("models/model.onnx", MODEL);

        long modified = installed.lastModified();
        try (RandomAccessFile file = new RandomAccessFile(installed, "rw")) { file.write(99); }
        check(installed.setLastModified(modified + 3000), "could not perturb cached model mtime");
        ModelInstaller.prepare(context, null, null);
        check(Arrays.equals(MODEL, Files.readAllBytes(installed.toPath())), "modified cache was trusted");
        check(context.getAssets().modelBytesRead == bytesRead + MODEL.length, "modified cache not reverified");

        Files.write(marker.toPath(), "broken JSON".getBytes(StandardCharsets.UTF_8));
        ModelInstaller.prepare(context, null, null);
        check(context.getAssets().modelBytesRead == bytesRead + MODEL.length * 2L, "invalid marker was trusted");
        Files.write(new File(installed.getParentFile(), "model.onnx.partial").toPath(), new byte[11]);
        ModelInstaller.prepare(context, null, null);
        check(!new File(installed.getParentFile(), "model.onnx.partial").exists(), "stale partial not removed");

        expectFailure(fixture(base, "truncated", manifest(), Arrays.copyOf(MODEL, 37)), "truncated model");
        JSONObject wrongHash = manifest();
        wrongHash.put("deployment_sha256", String.join("", Collections.nCopies(64, "0")));
        expectFailure(fixture(base, "hash", wrongHash, MODEL), "wrong SHA");
        JSONObject wrongBytes = manifest();
        wrongBytes.put("deployment_bytes", MODEL.length - 1);
        expectFailure(fixture(base, "long", wrongBytes, MODEL), "too many bytes");
        JSONObject wrongIdentity = manifest();
        wrongIdentity.put("source_sha256", hash);
        expectFailure(fixture(base, "identity", wrongIdentity, MODEL), "source identity");
        JSONObject wrongType = manifest();
        wrongType.put("deployment_bytes", String.valueOf(MODEL.length));
        expectFailure(fixture(base, "type", wrongType, MODEL), "numeric string byte count");
        JSONObject wrongFallback = manifest();
        wrongFallback.getJSONObject("metadata").put("openpilot.allow_cpu_fallback", "1");
        expectFailure(fixture(base, "fallback", wrongFallback, MODEL), "CPU fallback manifest");

        Context canceled = fixture(base, "cancel", manifest(), MODEL);
        final boolean[] stop = {false};
        List<Integer> cancellationProgress = new ArrayList<>();
        try {
            ModelInstaller.prepare(canceled, percent -> {
                cancellationProgress.add(percent);
                if (percent > 0) stop[0] = true;
            }, () -> stop[0]);
            throw new AssertionError("cancellation ignored");
        } catch (InterruptedIOException expected) {
            check(!cancellationProgress.contains(100), "canceled copy signalled ready");
            File canceledDirectory = new File(new File(canceled.getFilesDir(), "models"), hash);
            check(!new File(canceledDirectory, "model.onnx").exists(), "canceled model published");
            check(!new File(canceledDirectory, "model.onnx.partial").exists(), "canceled partial survived");
            check(!new File(canceledDirectory, "verified.json").exists(), "canceled marker published");
        }
        check(ModelInstaller.prepare(canceled, null, null).isFile(), "retry after cancellation failed");

        Context noSpace = fixture(base, "space", manifest(), MODEL);
        StatFs.available = MODEL.length;
        try {
            expectFailure(noSpace, "insufficient reserved space");
            check(noSpace.getAssets().modelBytesRead == 0, "low-space installation started copying");
        } finally { StatFs.available = Long.MAX_VALUE; }

        Thread.currentThread().interrupt();
        try {
            ModelInstaller.prepare(context, null, null);
            throw new AssertionError("thread interrupt ignored");
        } catch (InterruptedIOException expected) {
            check(Thread.currentThread().isInterrupted(), "interruption status cleared");
        } finally { Thread.interrupted(); }
        System.out.println("ModelInstaller host checks passed: " + checks);
    }
}
"""


class ModelInstallerHostTests(unittest.TestCase):
    def test_install_reuse_recovery_and_failure_paths(self):
        json_jar = os.environ.get("JSON_JAR")
        if not json_jar or not Path(json_jar).is_file():
            self.skipTest("Set JSON_JAR to a host org.json jar for ModelInstaller JVM checks")
        kotlin_home = TOOLS / "kotlin"
        kotlinc = kotlin_home / "bin/kotlinc"
        stdlib = kotlin_home / "lib/kotlin-stdlib.jar"
        annotations = kotlin_home / "lib/annotations-13.0.jar"
        if not all(path.is_file() for path in (kotlinc, stdlib, annotations)):
            self.skipTest("Run android/scripts/fetch_android_sdk.py and android/scripts/fetch_kotlin.py "
                          "(or android/scripts/build_apk.sh) to install the pinned build tools")
        cached_jdk = next(iter(sorted((TOOLS / "jdk").glob("*/Contents/Home/bin/java"))), None)
        if cached_jdk is None:
            cached_jdk = next(iter(sorted((TOOLS / "jdk").glob("*/bin/java"))), None)
        java = os.environ.get("JAVA") or (str(cached_jdk) if cached_jdk else shutil.which("java"))
        javac = os.environ.get("JAVAC") or (str(cached_jdk.with_name("javac")) if cached_jdk
                                           else shutil.which("javac"))
        if not javac or not java:
            self.skipTest("A host JDK is required for ModelInstaller JVM checks")
        compiler_env = dict(os.environ, JAVA_HOME=str(Path(java).resolve().parent.parent))

        def run(command, **kwargs):
            result = subprocess.run(command, capture_output=True, text=True, **kwargs)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return result

        with tempfile.TemporaryDirectory(prefix="model-installer-test-") as temporary:
            root = Path(temporary)
            sources = []
            for name, source in {**STUBS, "ModelInstallerHostTest.java": HARNESS}.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(source)
                sources.append(str(path))
            loader = ANDROID / "app/src/main/kotlin/com/example/openpilotinference/android/ModelInstaller.kt"
            classes = root / "classes"
            harness = str(root / "ModelInstallerHostTest.java")
            stub_sources = [source for source in sources if source != harness]
            run([javac, "--release", "8", "-Xlint:-options", "-d", str(classes), *stub_sources])
            classpath = os.pathsep.join([str(classes), json_jar, str(stdlib), str(annotations)])
            run([str(kotlinc), "-jvm-target", "1.8", "-no-stdlib", "-no-reflect",
                 "-classpath", classpath, "-d", str(classes), str(loader)], env=compiler_env)
            run([javac, "--release", "8", "-Xlint:-options", "-classpath", classpath,
                 "-d", str(classes), harness])
            data = root / "data"
            data.mkdir()
            result = run([java, "-classpath", classpath, "ModelInstallerHostTest", str(data)])
            self.assertIn("ModelInstaller host checks passed:", result.stdout)
            print(result.stdout.strip())


if __name__ == "__main__":
    unittest.main()
