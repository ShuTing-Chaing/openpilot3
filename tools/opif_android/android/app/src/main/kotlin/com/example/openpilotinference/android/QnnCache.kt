package com.example.openpilotinference.android

import android.content.Context
import android.os.Build
import java.io.File
import java.security.MessageDigest

/** Identity of the verified model, device build and actual packaged QNN runtime. */
internal object QnnCache {
    data class Location(val directory: String, val identity: String)

    // Called on the service worker; never hashes libraries on the UI thread.
    fun location(context: Context, model: File): Location {
        val digest = MessageDigest.getInstance("SHA-256")
        fun field(value: String) {
            digest.update(value.toByteArray(Charsets.UTF_8))
            digest.update(0.toByte())
        }
        val deployment = requireNotNull(model.parentFile).name
        require(deployment.length == 64 && deployment.all { it in '0'..'9' || it in 'a'..'f' }) {
            "Expected a verified model deployment directory"
        }
        field("opif-qnn-cache-v1")
        field(deployment)
        field(Build.FINGERPRINT)
        field(Build.SOC_MODEL)
        field(Build.HARDWARE)
        field(System.getProperty("os.version", "") ?: "")
        val buffer = ByteArray(256 * 1024)
        for (name in arrayOf("libopif_jni.so", "libonnxruntime.so", "libonnxruntime_providers_qnn.so", "libQnnHtp.so",
            "libQnnHtpPrepare.so", "libQnnSystem.so", "libQnnHtpV81Skel.so", "libQnnHtpV81Stub.so")) {
            field(name)
            val libraryDigest = MessageDigest.getInstance("SHA-256")
            File(context.applicationInfo.nativeLibraryDir, name).inputStream().use { input ->
                while (true) {
                    val count = input.read(buffer)
                    if (count < 0) break
                    libraryDigest.update(buffer, 0, count)
                }
            }
            digest.update(libraryDigest.digest())
        }
        val hex = "0123456789abcdef"
        val identity = buildString(64) {
            for (byte in digest.digest()) {
                val value = byte.toInt() and 255
                append(hex[value ushr 4])
                append(hex[value and 15])
            }
        }
        return Location(File(context.cacheDir, "qnn-context").absolutePath, identity)
    }
}
