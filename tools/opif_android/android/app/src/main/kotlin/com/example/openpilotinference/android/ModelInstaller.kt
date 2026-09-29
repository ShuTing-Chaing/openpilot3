package com.example.openpilotinference.android

import android.content.Context
import android.content.res.AssetManager
import android.os.StatFs
import org.json.JSONException
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.FileInputStream
import java.io.FileOutputStream
import java.io.IOException
import java.io.InputStream
import java.io.InterruptedIOException
import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import java.security.NoSuchAlgorithmException

/** Installs the complete bundled graph. Call [prepare] from a worker thread. */
object ModelInstaller {
    fun interface Progress {
        /** Integer percentage; 100 means both graph and verified marker were published. */
        fun update(percent: Int)
    }

    fun interface Cancelled {
        fun isCancelled(): Boolean
    }

    private const val MODEL_ID = "cinque-v3-big"
    private const val SOURCE_SHA256 =
        "404a18cfd86d29637d20c697dfde245bb47c666ae016730ab674c65f4d1e1aa4"
    private const val MODEL_ASSET = "models/model.onnx"
    private const val MANIFEST_ASSET = "models/manifest.json"
    private const val MANIFEST_LIMIT = 64 * 1024
    private const val MARKER_LIMIT = 8 * 1024
    private const val COPY_BUFFER_BYTES = 1024 * 1024
    private const val SPACE_RESERVE_BYTES = 32L * 1024 * 1024
    private const val MAX_MODEL_BYTES = 2L * 1024 * 1024 * 1024

    /**
     * Returns only a completely verified, app-private model file. Source identity
     * is pinned here; the signed APK manifest supplies the exported file digest.
     * A private marker permits later starts to check identity, size and mtime
     * without hashing all 729 MiB again. It is a cache record, not protection
     * against another process already able to modify this app's private files.
     *
     * This method is serialized because the service and an activity may request
     * initialization concurrently. This application uses a single Android process.
     * Cancellation throws [InterruptedIOException] and never publishes a partial
     * model as ready. A fully verified copy interrupted before marker publication
     * is deliberately copied and verified again on the next attempt.
     */
    @JvmStatic
    @Synchronized
    @Throws(IOException::class)
    fun prepare(context: Context?, callback: Progress?, cancellation: Cancelled?): File {
        if (context == null) {
            throw IOException("Model installation requires an application context")
        }
        checkCancelled(cancellation)
        report(callback, 0)
        val assets = context.assets
        val expected = assets.open(MANIFEST_ASSET, AssetManager.ACCESS_STREAMING).use {
            parseManifest(readBounded(it, MANIFEST_LIMIT))
        }
        checkCancelled(cancellation)

        // Open even on a cache hit: an APK missing its bundled model must fail.
        assets.open(MODEL_ASSET, AssetManager.ACCESS_STREAMING).use { modelInput ->
            val filesDirectory = context.filesDir
                ?: throw IOException("Private application storage is unavailable")
            val root = File(filesDirectory, "models")
            val directory = File(root, expected.deploymentSha256)
            ensureDirectory(directory)
            val model = File(directory, "model.onnx")
            val marker = File(directory, "verified.json")
            val partialModel = File(directory, "model.onnx.partial")
            val partialMarker = File(directory, "verified.json.partial")
            // A process killed while writing leaves only these unpublished files.
            removeStale(partialModel)
            removeStale(partialMarker)
            if (matchesVerifiedMarker(model, marker, expected)) {
                checkCancelled(cancellation)
                report(callback, 100)
                return model
            }
            removeStale(marker)
            checkSpace(directory, expected.deploymentBytes)
            try {
                copyAndVerify(modelInput, partialModel, expected, callback, cancellation)
                checkCancelled(cancellation)
                atomicReplace(partialModel, model)
                checkCancelled(cancellation)
                if (!model.isFile || model.length() != expected.deploymentBytes || model.lastModified() <= 0) {
                    throw IOException("Installed model file metadata is invalid")
                }
                writeMarker(partialMarker, model, expected)
                checkCancelled(cancellation)
                atomicReplace(partialMarker, marker)
                checkCancelled(cancellation)
                report(callback, 100)
                return model
            } finally {
                // Preserve the original exception if cleanup cannot complete;
                // the next invocation fails explicitly when stale removal fails.
                partialModel.delete()
                partialMarker.delete()
            }
        }
    }

    private fun copyAndVerify(
        source: InputStream,
        destination: File,
        expected: Manifest,
        callback: Progress?,
        cancellation: Cancelled?,
    ) {
        val digest = newSha256()
        val buffer = ByteArray(COPY_BUFFER_BYTES)
        var copied = 0L
        var lastPercent = 0
        FileOutputStream(destination).use { output ->
            while (true) {
                checkCancelled(cancellation)
                val count = source.read(buffer)
                if (count == -1) break
                if (count == 0) continue
                if (count > expected.deploymentBytes - copied) {
                    throw IOException("Bundled model exceeds manifest byte count")
                }
                output.write(buffer, 0, count)
                digest.update(buffer, 0, count)
                copied += count
                val percent = minOf(99L, copied * 100 / expected.deploymentBytes).toInt()
                if (percent != lastPercent) {
                    report(callback, percent)
                    lastPercent = percent
                }
            }
            checkCancelled(cancellation)
            if (copied != expected.deploymentBytes) {
                throw IOException(
                    "Bundled model is incomplete: expected ${expected.deploymentBytes} bytes, received $copied"
                )
            }
            if (expected.deploymentSha256 != hex(digest.digest())) {
                throw IOException("Bundled model SHA-256 does not match its manifest")
            }
            output.flush()
            output.fd.sync()
        }
    }

    private fun matchesVerifiedMarker(model: File, marker: File, expected: Manifest): Boolean {
        if (!model.isFile || !marker.isFile || model.length() != expected.deploymentBytes
            || model.lastModified() <= 0
        ) {
            return false
        }
        return try {
            FileInputStream(marker).use { input ->
                val stamp = JSONObject(String(readBounded(input, MARKER_LIMIT), StandardCharsets.UTF_8))
                integer(stamp, "schema_version") == 1L
                    && MODEL_ID == stamp.getString("model_id")
                    && SOURCE_SHA256 == stamp.getString("source_sha256")
                    && expected.manifestSha256 == stamp.getString("manifest_sha256")
                    && expected.deploymentSha256 == stamp.getString("deployment_sha256")
                    && integer(stamp, "deployment_bytes") == expected.deploymentBytes
                    && integer(stamp, "last_modified_ms") == model.lastModified()
            }
        } catch (_: IOException) {
            false
        } catch (_: JSONException) {
            false
        } catch (_: IllegalArgumentException) {
            false
        }
    }

    private fun writeMarker(destination: File, model: File, expected: Manifest) {
        try {
            val stamp = JSONObject()
                .put("schema_version", 1)
                .put("model_id", MODEL_ID)
                .put("source_sha256", SOURCE_SHA256)
                .put("manifest_sha256", expected.manifestSha256)
                .put("deployment_sha256", expected.deploymentSha256)
                .put("deployment_bytes", expected.deploymentBytes)
                .put("last_modified_ms", model.lastModified())
            FileOutputStream(destination).use { output ->
                output.write(stamp.toString().toByteArray(StandardCharsets.UTF_8))
                output.flush()
                output.fd.sync()
            }
        } catch (invalidMarker: JSONException) {
            throw IOException("Cannot encode verified model marker", invalidMarker)
        }
    }

    private fun ensureDirectory(directory: File) {
        if (!directory.isDirectory && !directory.mkdirs() && !directory.isDirectory) {
            throw IOException("Cannot create private model directory")
        }
    }

    private fun removeStale(file: File) {
        if (file.exists() && !file.delete()) {
            throw IOException("Cannot remove incomplete model cache file: ${file.name}")
        }
    }

    private fun atomicReplace(source: File, destination: File) {
        // Both files are in the same app-private directory; Android implements
        // File.renameTo with the atomic POSIX rename operation, replacing a file.
        if (!source.renameTo(destination)) {
            throw IOException("Cannot publish verified model file: ${destination.name}")
        }
    }

    private fun checkSpace(directory: File, modelBytes: Long) {
        val available = try {
            StatFs(directory.absolutePath).availableBytes
        } catch (unavailable: IllegalArgumentException) {
            throw IOException("Cannot inspect available model storage", unavailable)
        }
        val required = modelBytes + SPACE_RESERVE_BYTES
        if (available < required) {
            throw IOException("Insufficient private storage for model: need $required available bytes, have $available")
        }
    }

    private fun readBounded(input: InputStream, limit: Int): ByteArray {
        val output = ByteArrayOutputStream()
        val buffer = ByteArray(4096)
        while (true) {
            val count = input.read(buffer)
            if (count == -1) break
            if (count > limit - output.size()) {
                throw IOException("Model manifest or cache marker is too large")
            }
            output.write(buffer, 0, count)
        }
        return output.toByteArray()
    }

    private fun integer(json: JSONObject, name: String): Long {
        val value = json.get(name)
        if (value !is Int && value !is Long) {
            throw JSONException("Expected integer field: $name")
        }
        return (value as Number).toLong()
    }

    private fun checkCancelled(cancellation: Cancelled?) {
        if (Thread.currentThread().isInterrupted || cancellation?.isCancelled() == true) {
            throw InterruptedIOException("Model preparation cancelled")
        }
    }

    private fun report(callback: Progress?, percent: Int) {
        callback?.update(percent)
    }

    private fun newSha256(): MessageDigest = try {
        MessageDigest.getInstance("SHA-256")
    } catch (unavailable: NoSuchAlgorithmException) {
        throw IOException("SHA-256 is unavailable", unavailable)
    }

    private fun hex(bytes: ByteArray): String {
        val alphabet = "0123456789abcdef"
        val result = CharArray(bytes.size * 2)
        for (index in bytes.indices) {
            val unsigned = bytes[index].toInt() and 0xff
            result[index * 2] = alphabet[unsigned ushr 4]
            result[index * 2 + 1] = alphabet[unsigned and 0xf]
        }
        return String(result)
    }

    private class Manifest(
        val deploymentSha256: String,
        val deploymentBytes: Long,
        val manifestSha256: String,
    )

    private fun parseManifest(raw: ByteArray): Manifest {
        try {
            val manifest = JSONObject(String(raw, StandardCharsets.UTF_8))
            val metadata = manifest.getJSONObject("metadata")
            if (integer(manifest, "schema_version") != 1L
                || MODEL_ID != manifest.getString("model_id")
                || SOURCE_SHA256 != manifest.getString("source_sha256")
                || "model.onnx" != manifest.getString("model_file")
                || "fp16-original" != manifest.getString("precision")
                || manifest.get("quantized") != false
                || manifest.get("host_state_updates") != false
                || MODEL_ID != metadata.getString("openpilot.model_id")
                || SOURCE_SHA256 != metadata.getString("openpilot.source_sha256")
                || "1" != metadata.getString("openpilot.abi_version")
                || "fp16-original" != metadata.getString("openpilot.precision")
                || "0" != metadata.getString("openpilot.allow_cpu_fallback")
            ) {
                throw IOException("Bundled manifest is not the pinned complete Cinque v3 model")
            }
            val hash = manifest.getString("deployment_sha256")
            val bytes = integer(manifest, "deployment_bytes")
            if (!hash.matches(Regex("[0-9a-f]{64}")) || bytes <= 0 || bytes > MAX_MODEL_BYTES) {
                throw IOException("Bundled manifest has an invalid deployment digest or byte count")
            }
            return Manifest(hash, bytes, hex(newSha256().digest(raw)))
        } catch (invalidManifest: JSONException) {
            throw IOException("Bundled model manifest is missing or malformed", invalidManifest)
        }
    }
}
