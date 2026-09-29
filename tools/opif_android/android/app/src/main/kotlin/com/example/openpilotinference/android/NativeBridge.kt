package com.example.openpilotinference.android

internal object NativeBridge {
    init { System.loadLibrary("opif_jni") }

    interface Callback {
        fun onState(state: String, detail: String, listeningTransport: Int)
        fun onStats(connected: Boolean, frames: Long, inferenceMs: Double)
        fun onPreview(packed: ByteArray, requestId: Long, sessionId: Long, epoch: Long, eofNs: Long)
        fun onPerformance(inferenceMs: DoubleArray, completionNs: LongArray)
    }

    // Keep static native JVM methods and their names for the existing C++ JNI exports.
    @JvmStatic external fun createRun(): Long
    @JvmStatic external fun setTransport(token: Long, mode: Int)
    @JvmStatic external fun run(token: Long, modelPath: String, nativeLibDir: String,
        cacheDir: String, cacheIdentity: String, callback: Callback)
    @JvmStatic external fun requestStop(token: Long)
    @JvmStatic external fun releaseRun(token: Long)
    @JvmStatic external fun setPreviewEnabled(enabled: Boolean)
    @JvmStatic external fun renderPreview(packed: ByteArray, pixels: IntArray)
}
