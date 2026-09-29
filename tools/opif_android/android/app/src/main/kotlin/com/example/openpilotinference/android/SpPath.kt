package com.example.openpilotinference.android

import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.max
import kotlin.math.min

/** Display-only wire data; never exported to model state or vehicle control. */
internal data class SpPath(
    val source: Int, val flags: Int, val publishSeq: Long, val sessionId: Long,
    val epoch: Long, val requestId: Long, val eofNs: Long, val narrowFrame: Long,
    val wideFrame: Long, val captureAgeMs: Float, val height: Float, val blend: Float,
    val expiresNs: Long, val matrices: FloatArray, val points: FloatArray, val acceleration: FloatArray,
) {
    val sourceLabel: String get() = if (source == 2) "SP 大模型路径" else "SP 小模型路径"
    fun matches(session: Long, stateEpoch: Long, request: Long, eof: Long, now: Long): Boolean =
        sessionId == session && epoch == stateEpoch && eofNs == eof &&
        (source == 1 && requestId == 0L || source == 2 && requestId == request) &&
        now < expiresNs && flags and 3 == 3

    /** SP half width 0.9m and height; matrices map into each 512x256 model input. */
    fun polygon(camera: Int): FloatArray {
        if (camera !in 0..1) return FloatArray(0)
        val left = ArrayList<Float>(66); val right = ArrayList<Float>(66)
        val maxDistance = max(10f, min(100f, points[96]))
        val m = camera * 9
        for (i in 0 until 33) {
            val x = points[3*i]; val y = points[3*i+1]; val z = points[3*i+2]+height
            if (x < 0 || x > maxDistance) continue
            val projected = ArrayList<Float>(4)
            for (offset in floatArrayOf(-.9f, .9f)) {
                val py = y + offset
                val depth = matrices[m+6]*x + matrices[m+7]*py + matrices[m+8]*z
                if (depth <= 1e-3f) break
                val u = (matrices[m]*x + matrices[m+1]*py + matrices[m+2]*z)/depth
                val v = (matrices[m+3]*x + matrices[m+4]*py + matrices[m+5]*z)/depth
                if (!u.isFinite() || !v.isFinite() || u !in -500f..1012f || v !in -500f..756f) break
                projected.add(u); projected.add(v)
            }
            if (projected.size != 4) continue
            left.add(projected[0]); left.add(projected[1]); right.add(projected[2]); right.add(projected[3])
        }
        if (left.size < 4) return FloatArray(0)
        val result = ArrayList<Float>(left.size + right.size); result.addAll(left)
        for (i in right.size-2 downTo 0 step 2) { result.add(right[i]); result.add(right[i+1]) }
        return result.toFloatArray()
    }
}

internal object SpPathProtocol {
    const val PORT = 5556
    const val BYTES = 672
    fun decode(bytes: ByteArray, receivedNs: Long): SpPath? {
        if (bytes.size != BYTES || receivedNs < 0) return null
        val b = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
        if (b.int != 0x31525053 || b.get().toInt() != 1) return null // SPR1
        val source=b.get().toInt(); val flags=b.short.toInt() and 65535
        if (source !in 1..2 || flags and 31 != flags) return null
        val seq=b.long; val session=b.long; val epoch=b.long; val request=b.long; val eof=b.long
        val narrow=b.int.toLong() and 0xffffffffL; val wide=b.int.toLong() and 0xffffffffL
        val age=b.float; val height=b.float; val blend=b.float
        val ttl=b.short.toInt() and 65535; val count=b.short.toInt() and 65535
        if (seq <= 0 || session == 0L || epoch <= 0 || eof <= 0 ||
            (source == 1 && request != 0L) || (source == 2 && request <= 0) ||
            !age.isFinite() || age !in 0f..200f || !height.isFinite() || height !in .2f..4f ||
            !blend.isFinite() || blend !in 0f..1f || ttl !in 1..200 || count != 33) return null
        val matrices=FloatArray(18){b.float}; val points=FloatArray(99){b.float};val acceleration=FloatArray(33){b.float}
        if (!matrices.all{it.isFinite()} || !points.all{it.isFinite()} || !acceleration.all{it.isFinite()}) return null
        if (points.asList().chunked(3).any{ kotlin.math.abs(it[0])>1000f || kotlin.math.abs(it[1])>200f || kotlin.math.abs(it[2])>200f }) return null
        return SpPath(source,flags,seq,session,epoch,request,eof,narrow,wide,age,height,blend,
            receivedNs+ttl*1_000_000L,matrices,points,acceleration)
    }
}
