package com.example.openpilotinference.android

import kotlin.math.abs
import kotlin.math.max

private fun near(actual: Double, expected: Double) {
    check(abs(actual - expected) < 1e-8) { "Expected $expected, got $actual" }
}
private fun awaitSnapshot(completionNs: Long): PerformanceHistory.Snapshot {
    val deadline = System.nanoTime() + 2_000_000_000L
    while (true) {
        PerformanceHistory.current?.let { if (it.completionNs == completionNs) return it }
        check(System.nanoTime() < deadline) { "Statistics worker timed out" }
        Thread.sleep(1)
    }
}
private fun checkWindow(fps: Int) {
    val base = 50_000_000_000L
    val frames = LongArray(fps * 18 + 1) { base + it * 1_000_000_000L / fps }
    val buckets = FpsBuckets()
    for (end in frames.indices step fps / 2) {
        val snapshot = frames.copyOfRange(max(0, end - 255), end + 1)
        buckets.append(snapshot)
        val bars = buckets.bars(frames[end])
        check(bars.rates.size <= 20)
        if (end >= fps * 10) {
            check(bars.rates.size == 20) { "$fps FPS did not retain a complete ten seconds" }
            check(bars.startsNs.last() - bars.startsNs.first() == 9_500_000_000L)
            bars.rates.forEach { near(it.toDouble(), fps.toDouble()) }
        }
        // A repeated or overlapping native snapshot must not inflate the result.
        buckets.append(snapshot)
        check(buckets.bars(frames[end]).rates.contentEquals(bars.rates))
    }
    val last = frames.last()
    check(buckets.bars(last + FpsBuckets.WINDOW_NS).rates.isEmpty()) { "Idle history did not expire" }
    buckets.clear()
    buckets.append(longArrayOf(last + 1_000_000_000L))
    check(buckets.bars(last + 1_000_000_000L).rates.isEmpty()) { "First frame created a fabricated FPS bar" }
    buckets.append(longArrayOf(last + 1_000_000_000L, last + 1_250_000_000L))
    check(buckets.bars(last + 1_250_000_000L).rates.isEmpty()) { "Partial bucket was treated as a full bucket" }
    buckets.append(longArrayOf(last + 1_500_000_000L))
    val resetBars = buckets.bars(last + 1_500_000_000L)
    check(resetBars.rates.size == 1)
    near(resetBars.rates.single().toDouble(), 4.0)
    check(resetBars.startsNs.single() == last + 1_000_000_000L)
}
private fun checkCadence(refreshHz: Int) {
    val cadence = PlotCadence()
    var renders = 0
    val start = 1_000_000_000L
    for (frame in 0 until refreshHz * 10) {
        if (cadence.due(start + frame * 1_000_000_000L / refreshHz)) renders++
    }
    check(renders in 599..601) { "$refreshHz Hz display rendered $renders times in ten seconds" }
    cadence.reset()
    check(cadence.due(start))
    check(!cadence.due(start + 1))
    check(cadence.due(start + 1_000_000_000L)) { "Long pause did not recover" }
}
fun main() {
    checkWindow(20)
    checkWindow(60)
    listOf(60, 90, 120, 144).forEach(::checkCadence)
    check(FpsBuckets.axisMaximum(20.0) == 25.0)
    check(FpsBuckets.axisMaximum(120.0) > 120.0) { "FPS axis was fixed to 60" }
    val now = System.nanoTime()
    PerformanceHistory.beginRun(101)
    val completions = LongArray(201) { now - 10_000_000_000L + it * 50_000_000L }
    PerformanceHistory.offer(101, DoubleArray(201) { 20.0 }, completions)
    val original = awaitSnapshot(now)
    check(original.rates.size == 20)
    near(original.p50, 20.0)
    near(original.p99, 20.0)
    near(original.fps, 20.0)
    PerformanceHistory.endRun(101)
    check(PerformanceHistory.current === original) { "Stop discarded the last latency window" }
    PerformanceHistory.beginRun(102)
    check(PerformanceHistory.current == null)
    PerformanceHistory.offer(101, doubleArrayOf(99.0), longArrayOf(now + 1))
    Thread.sleep(20)
    check(PerformanceHistory.current == null) { "Old run was accepted" }
    PerformanceHistory.offer(102, doubleArrayOf(10.0), longArrayOf(now + 2))
    val single = awaitSnapshot(now + 2)
    check(single.rates.isEmpty() && single.fps == 0.0)
    PerformanceHistory.resetSession(102)
    check(PerformanceHistory.current == null)
    PerformanceHistory.offer(102, doubleArrayOf(11.0, 12.0), longArrayOf(now + 3, now + 250_000_003))
    val reset = awaitSnapshot(now + 250_000_003)
    check(reset.rates.isEmpty()) { "Session reset inherited old buckets" }
    near(reset.p50, 11.5)
    near(reset.p99, 11.99)
    println("PASS: 20/60 FPS ten-second history, 256-frame overlap deduplication, first/partial buckets, idle expiry, run/session reset, p50/p99, 60 Hz cadence on 60/90/120/144 Hz displays")
}
