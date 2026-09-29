package com.example.openpilotinference.android

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.os.Process
import android.util.TypedValue
import android.view.Choreographer
import android.view.View
import java.util.Locale
import java.util.concurrent.Executors
import kotlin.math.ceil
import kotlin.math.floor
import kotlin.math.log10
import kotlin.math.max
import kotlin.math.pow

/** Incremental, fixed-memory history, independent of the native 256-completion ring. */
internal class FpsBuckets {
    data class Bars(val startsNs: LongArray, val rates: FloatArray)
    companion object {
        const val WIDTH_NS = 500_000_000L
        const val WINDOW_NS = 10_000_000_000L
        private const val CAPACITY = 21 // Twenty completed buckets plus the bucket being filled.

        fun axisMaximum(value: Double): Double {
            val desired = max(1.0, value * 1.08)
            val unit = 10.0.pow(floor(log10(desired)))
            val scaled = desired / unit
            val step = when {
                scaled <= 1.0 -> 1.0
                scaled <= 2.0 -> 2.0
                scaled <= 2.5 -> 2.5
                scaled <= 5.0 -> 5.0
                else -> 10.0
            }
            return step * unit
        }
    }
    private val ids = LongArray(CAPACITY) { -1L }
    private val counts = IntArray(CAPACITY)
    private var originNs = 0L
    private var lastNs = 0L

    fun clear() {
        ids.fill(-1L)
        counts.fill(0)
        originNs = 0L
        lastNs = 0L
    }

    fun append(completions: LongArray) {
        for (timestamp in completions) {
            if (timestamp <= lastNs) continue // Overlapping native snapshots never double-count.
            if (originNs == 0L) {
                // A single completion defines the observation start, not an FPS of zero or infinity.
                originNs = timestamp
                lastNs = timestamp
                continue
            }
            // Bins are (start, end]; the completion establishing the origin is excluded.
            val id = (timestamp - originNs - 1L) / WIDTH_NS
            val slot = (id % CAPACITY).toInt()
            if (ids[slot] != id) { ids[slot] = id; counts[slot] = 0 }
            counts[slot]++
            lastNs = timestamp
        }
    }

    fun bars(nowNs: Long): Bars {
        if (originNs == 0L || nowNs - lastNs >= WINDOW_NS) return Bars(LongArray(0), FloatArray(0))
        // Never compare a partially filled half-second bucket with a completed bucket.
        val completed = (lastNs - originNs) / WIDTH_NS - 1L
        val first = max(0L, completed - 19L)
        if (completed < first) return Bars(LongArray(0), FloatArray(0))
        val starts = LongArray((completed - first + 1L).toInt())
        val rates = FloatArray(starts.size)
        for (i in starts.indices) {
            val id = first + i
            val slot = (id % CAPACITY).toInt()
            starts[i] = originNs + id * WIDTH_NS
            rates[i] = if (ids[slot] == id) counts[slot] * 2f else 0f
        }
        return Bars(starts, rates)
    }
}

/** A phase-preserving 60 Hz limit: 90 Hz displays render two of every three vsyncs. */
internal class PlotCadence {
    private var nextNs = 0L
    fun reset() { nextNs = 0L }
    fun due(frameNs: Long): Boolean {
        val period = 1_000_000_000.0 / 60.0
        if (nextNs == 0L || frameNs - nextNs > 100_000_000L) nextNs = frameNs
        if (frameNs < nextNs) return false
        val periods = floor((frameNs - nextNs) / period).toLong() + 1L
        nextNs += (periods * period).toLong()
        return true
    }
}

internal object PerformanceHistory {
    data class Snapshot(val count: Int, val mean: Double, val last: Double, val p50: Double,
        val p99: Double, val fps: Double, val completionNs: Long, val maximumMs: Double,
        val maximumFps: Double, val x: FloatArray, val latency: FloatArray,
        val fpsStartsNs: LongArray, val rates: FloatArray)
    private data class Samples(val times: DoubleArray, val completions: LongArray, val generation: Long)
    private val lock = Any()
    private val worker = Executors.newSingleThreadExecutor { task ->
        Thread({ Process.setThreadPriority(Process.THREAD_PRIORITY_BACKGROUND); task.run() }, "opif-performance")
            .apply { isDaemon = true }
    }
    private var run = 0L
    private var generation = 0L
    private var pending: Samples? = null
    private var scheduled = false
    // Accessed exclusively by the calculation worker, including resets on a new generation.
    private val fpsBuckets = FpsBuckets()
    private var bucketGeneration = -1L
    @Volatile var current: Snapshot? = null
        private set

    fun beginRun(token: Long) = synchronized(lock) { run = token; clearLocked() }
    fun resetSession(token: Long) = synchronized(lock) { if (run == token) clearLocked() }
    fun endRun(token: Long) = synchronized(lock) {
        if (run == token) { run = 0L; generation++; pending = null }
    }
    private fun clearLocked() { generation++; pending = null; current = null }

    fun offer(token: Long, times: DoubleArray, completions: LongArray): Unit = synchronized(lock) {
        if (run != token || times.isEmpty() || times.size > 256 || times.size != completions.size) return
        pending = Samples(times, completions, generation)
        if (!scheduled) { scheduled = true; worker.execute { calculate() } }
    }

    private fun calculate() {
        while (true) {
            val samples = synchronized(lock) {
                val next = pending
                pending = null
                if (next == null) { scheduled = false; return }
                next
            }
            val t = samples.times
            val ns = samples.completions
            if (t.any { !it.isFinite() || it < 0.0 } || ns.indices.any { ns[it] <= 0 || (it > 0 && ns[it] <= ns[it - 1]) }) continue
            if (bucketGeneration != samples.generation) {
                fpsBuckets.clear()
                bucketGeneration = samples.generation
            }
            fpsBuckets.append(ns)
            val bars = fpsBuckets.bars(System.nanoTime())
            val sorted = t.sortedArray()
            fun quantile(q: Double): Double {
                val position = q * (sorted.size - 1)
                val low = floor(position).toInt()
                val high = ceil(position).toInt()
                return sorted[low] + (sorted[high] - sorted[low]) * (position - low)
            }
            val n = t.size
            val span = max(1L, ns.last() - ns.first())
            val x = FloatArray(n) { if (n == 1) 1f else ((ns[it] - ns.first()).toDouble() / span).toFloat() }
            var start = 0
            while (start < n - 1 && ns.last() - ns[start] > 2_000_000_000L) start++
            val fps = if (start < n - 1) (n - 1 - start) * 1e9 / (ns.last() - ns[start]) else 0.0
            val maximumMs = FpsBuckets.axisMaximum(t.max())
            val maximumFps = FpsBuckets.axisMaximum(bars.rates.maxOrNull()?.toDouble() ?: 0.0)
            val result = Snapshot(n, t.average(), t.last(), quantile(.5), quantile(.99), fps,
                ns.last(), maximumMs, maximumFps, x, FloatArray(n) { (t[it] / maximumMs).toFloat() },
                bars.startsNs, bars.rates)
            synchronized(lock) { if (samples.generation == generation) current = result }
        }
    }
}

/** Drawing uses immutable 2 Hz snapshots; animation only changes the time-to-pixel transform. */
internal class PerformancePlot(context: Context) : View(context) {
    private val density = resources.displayMetrics.density
    private val grid = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.rgb(49, 60, 56); strokeWidth = density }
    private val labels = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(133, 156, 144)
        textSize = TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_SP, 10f, resources.displayMetrics)
    }
    private val latency = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(117, 225, 170); strokeWidth = 1.5f * density; style = Paint.Style.STROKE
        strokeJoin = Paint.Join.ROUND
    }
    private val latencyFill = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.argb(24, 117, 225, 170) }
    private val rate = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.rgb(111, 180, 236) }
    private val latencyPath = Path()
    private val fillPath = Path()
    private val choreographer = Choreographer.getInstance()
    private val cadence = PlotCadence()
    private var callbackPending = false
    private var geometryDirty = true
    private var latencyMaximumLabel = "—"
    private var fpsMaximumLabel = "—"
    private var fpsMiddleLabel = "—"
    private val frameCallback = object : Choreographer.FrameCallback {
        override fun doFrame(frameTimeNanos: Long) {
            callbackPending = false
            if (!canAnimate(System.nanoTime())) {
                invalidate() // One final draw removes bars that have just left the window.
                cadence.reset()
                return
            }
            if (cadence.due(frameTimeNanos)) invalidate()
            callbackPending = true
            choreographer.postFrameCallback(this)
        }
    }
    var snapshot: PerformanceHistory.Snapshot? = null
        set(value) {
            if (field === value) return
            field = value
            geometryDirty = true
            // Text and scale calculation happen only when the 2 Hz snapshot changes.
            latencyMaximumLabel = value?.let { axisText(it.maximumMs) } ?: "—"
            fpsMaximumLabel = value?.let { axisText(it.maximumFps) } ?: "—"
            fpsMiddleLabel = value?.let { axisText(it.maximumFps / 2.0) } ?: "—"
            updateAnimation()
            // Active snapshots are picked up by the existing cadence, not an extra 2 Hz draw.
            if (!callbackPending) invalidate()
        }

    private fun axisText(value: Double): String = if (value == floor(value)) value.toLong().toString()
        else String.format(Locale.ROOT, "%.1f", value)

    private fun canAnimate(nowNs: Long): Boolean = isAttachedToWindow && isShown && windowVisibility == VISIBLE &&
        snapshot?.let { nowNs - it.completionNs < FpsBuckets.WINDOW_NS } == true

    private fun updateAnimation() {
        if (canAnimate(System.nanoTime())) {
            if (!callbackPending) { callbackPending = true; choreographer.postFrameCallback(frameCallback) }
        } else if (callbackPending) {
            choreographer.removeFrameCallback(frameCallback)
            callbackPending = false
            cadence.reset()
        }
    }

    override fun onAttachedToWindow() { super.onAttachedToWindow(); updateAnimation() }
    override fun onDetachedFromWindow() {
        choreographer.removeFrameCallback(frameCallback)
        callbackPending = false
        cadence.reset()
        super.onDetachedFromWindow()
    }
    override fun onVisibilityChanged(changedView: View, visibility: Int) {
        super.onVisibilityChanged(changedView, visibility)
        if (isAttachedToWindow) updateAnimation()
    }
    override fun onWindowVisibilityChanged(visibility: Int) {
        super.onWindowVisibilityChanged(visibility)
        if (isAttachedToWindow) updateAnimation()
    }
    override fun onVisibilityAggregated(isVisible: Boolean) {
        super.onVisibilityAggregated(isVisible)
        updateAnimation()
    }
    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        super.onSizeChanged(w, h, oldw, oldh)
        geometryDirty = true
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val left = 36f * density
        val right = width - 5f * density
        if (right <= left || height <= 0) return
        val plotWidth = right - left
        val top = 7f * density
        val latencyBottom = height * .43f
        val fpsTop = height * .55f
        val fpsBottom = height - 15f * density
        val fpsHeight = fpsBottom - fpsTop
        if (latencyBottom <= top || fpsHeight <= 0f) return
        canvas.drawLine(left, latencyBottom, right, latencyBottom, grid)
        canvas.drawLine(left, fpsTop, right, fpsTop, grid)
        canvas.drawLine(left, fpsTop + fpsHeight / 2f, right, fpsTop + fpsHeight / 2f, grid)
        canvas.drawLine(left, fpsBottom, right, fpsBottom, grid)
        labels.textAlign = Paint.Align.RIGHT
        canvas.drawText(latencyMaximumLabel, left - 6f * density, top + labels.textSize, labels)
        canvas.drawText("0", left - 6f * density, latencyBottom, labels)
        canvas.drawText(fpsMaximumLabel, left - 6f * density, fpsTop + labels.textSize, labels)
        canvas.drawText(fpsMiddleLabel, left - 6f * density, fpsTop + fpsHeight / 2f + labels.textSize / 3f, labels)
        canvas.drawText("0", left - 6f * density, fpsBottom, labels)
        canvas.drawText("现在", right, height - 1f * density, labels)
        labels.textAlign = Paint.Align.LEFT
        canvas.drawText("−10 s", left, height - 1f * density, labels)
        val data = snapshot ?: return
        if (geometryDirty) {
            latencyPath.rewind()
            for (i in data.latency.indices) {
                val x = left + data.x[i] * plotWidth
                val y = top + (1f - data.latency[i]) * (latencyBottom - top)
                if (i == 0) latencyPath.moveTo(x, y) else latencyPath.lineTo(x, y)
            }
            fillPath.set(latencyPath)
            if (data.x.isNotEmpty()) {
                fillPath.lineTo(left + data.x.last() * plotWidth, latencyBottom)
                fillPath.lineTo(left + data.x.first() * plotWidth, latencyBottom)
                fillPath.close()
            }
            geometryDirty = false
        }
        canvas.drawPath(fillPath, latencyFill)
        canvas.drawPath(latencyPath, latency)
        val nowNs = System.nanoTime()
        if (nowNs - data.completionNs >= FpsBuckets.WINDOW_NS) return
        val windowStart = nowNs - FpsBuckets.WINDOW_NS
        val gap = 1.5f * density
        canvas.save()
        canvas.clipRect(left, fpsTop, right, fpsBottom)
        for (i in data.rates.indices) {
            if (data.rates[i] <= 0f) continue
            val x = left + ((data.fpsStartsNs[i] - windowStart).toDouble() / FpsBuckets.WINDOW_NS * plotWidth).toFloat()
            val end = x + (FpsBuckets.WIDTH_NS.toDouble() / FpsBuckets.WINDOW_NS * plotWidth).toFloat()
            if (end <= left || x >= right) continue
            val y = fpsBottom - (data.rates[i] / data.maximumFps).toFloat() * fpsHeight
            canvas.drawRoundRect(x + gap / 2f, y, end - gap / 2f, fpsBottom + 2f * density,
                2f * density, 2f * density, rate)
        }
        canvas.restore()
    }
}
