package com.example.openpilotinference.android

import java.io.FileDescriptor
import java.io.PrintWriter

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.Manifest
import android.content.Intent
import android.content.pm.ServiceInfo
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.net.wifi.WifiNetworkSpecifier
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import android.util.Log
import org.json.JSONObject
import java.io.File
import java.util.Locale
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

class InferenceService : Service() {
    private val main = Handler(Looper.getMainLooper())
    private val worker = Executors.newSingleThreadExecutor()
    private var job: RunJob? = null
    private var foreground = false
    private var destroyed = false
    private var wakeLock: PowerManager.WakeLock? = null
    private var hotspotCallback: ConnectivityManager.NetworkCallback? = null

    private class RunJob(val token: Long) {
        val cancelled = AtomicBoolean(false)
    }

    override fun onCreate() {
        super.onCreate()
        val channel = NotificationChannel(CHANNEL, "推理服务", NotificationManager.IMPORTANCE_LOW).apply {
            description = "显示模型和连接状态，并可停止服务"
        }
        requireNotNull(getSystemService(NotificationManager::class.java)).createNotificationChannel(channel)
        wakeLock = requireNotNull(getSystemService(PowerManager::class.java))
            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "$packageName:inference")
            .apply { setReferenceCounted(false) }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == STOP) {
            stopRun()
            return START_NOT_STICKY
        }
        // Foreground immediately, before extraction or native initialization.
        try {
            val currentNotification = notification(if (job == null) "正在启动推理服务" else ServerStatus.current.title())
            if (Build.VERSION.SDK_INT >= 34) {
                startForeground(NOTIFICATION, currentNotification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
            } else {
                startForeground(NOTIFICATION, currentNotification)
            }
            foreground = true
            requestHotspot()
            job?.let { run ->
                if (!run.cancelled.get()) {
                    val selected = ListenTransport.load(this)
                    NativeBridge.setTransport(run.token, selected.nativeValue)
                    // Keep the last confirmed listener until native observes the
                    // request. A -> B -> A can coalesce before its next poll.
                }
                return START_NOT_STICKY
            }
            check(Build.SOC_MODEL.uppercase(Locale.ROOT).startsWith("SM8850")) {
                "需要骁龙 8 Elite Gen 5（SM8850），当前设备：${Build.SOC_MODEL}"
            }
            requireNotNull(wakeLock).acquire()
            val run = RunJob(NativeBridge.createRun())
            job = run
            NativeBridge.setTransport(run.token, ListenTransport.load(this).nativeValue)
            InputPreview.beginRun(run.token)
            PerformanceHistory.beginRun(run.token)
            publish(ServerStatus("preparing", "首次启动需解包模型，之后会自动复用", 0, false, 0, 0.0))
            worker.execute { execute(run) }
        } catch (error: RuntimeException) {
            failStart(error)
        } catch (error: LinkageError) {
            failStart(error)
        }
        // A killed process must not silently restart a model or claim ready.
        return START_NOT_STICKY
    }

    private fun failStart(error: Throwable) {
        job?.let { run ->
            run.cancelled.set(true)
            NativeBridge.requestStop(run.token)
            NativeBridge.releaseRun(run.token)
            InputPreview.endRun(run.token)
            PerformanceHistory.endRun(run.token)
            job = null
        }
        publish(ServerStatus("error", message(error), 0, false, 0, 0.0))
        finishService()
    }

    private fun execute(run: RunJob) {
        try {
            val model = ModelInstaller.prepare(this,
                ModelInstaller.Progress { percent ->
                    main.post {
                        if (job === run && !run.cancelled.get() && !destroyed) {
                            publish(ServerStatus("preparing", "模型准备完成后将自动启动", percent, false, 0, 0.0))
                        }
                    }
                }, ModelInstaller.Cancelled { run.cancelled.get() })
            if (!run.cancelled.get()) {
                val cache = QnnCache.location(this, model)
                if (run.cancelled.get()) return
                if (run.cancelled.get()) return
                NativeBridge.run(run.token, model.absolutePath, applicationInfo.nativeLibraryDir,
                    cache.directory, cache.identity,
                    object : NativeBridge.Callback {
                        override fun onState(state: String, detail: String, listeningTransport: Int) {
                            // Native reports every session boundary, including a new START
                            // while already connected. Invalidate before accepting new frames.
                            InputPreview.resetSession(run.token)
                            if (state == "connected") PerformanceHistory.resetSession(run.token)
                            main.post {
                                if (job !== run || destroyed || run.cancelled.get()) return@post
                                val previous = ServerStatus.current
                                // Record what actually bound. The UI derives pending
                                // selection state without erasing this confirmation.
                                publish(previous.copy(phase = state, detail = detail,
                                    progress = 100, connected = state == "connected",
                                    listeningTransport = listeningTransport))
                            }
                        }

                        override fun onStats(connected: Boolean, frames: Long, inferenceMs: Double) {
                            main.post {
                                if (job !== run || destroyed || run.cancelled.get()) return@post
                                if (ServerStatus.current.listeningTransport !=
                                    ListenTransport.load(this@InferenceService).nativeValue) return@post
                                ServerStatus.current = ServerStatus.current.copy(progress = 100,
                                    connected = connected && ServerStatus.current.phase == "connected",
                                    frames = frames, inferenceMs = inferenceMs)
                            }
                        }

                        override fun onPreview(packed: ByteArray, requestId: Long, sessionId: Long, epoch: Long, eofNs: Long) {
                            if (!run.cancelled.get()) InputPreview.offer(run.token, packed, requestId, sessionId, epoch, eofNs)
                        }

                        override fun onPerformance(inferenceMs: DoubleArray, completionNs: LongArray) {
                            if (!run.cancelled.get()) PerformanceHistory.offer(run.token, inferenceMs, completionNs)
                        }
                    })
            }
        } catch (error: Exception) {
            reportFailure(run, error)
        } catch (error: LinkageError) {
            reportFailure(run, error)
        } finally {
            InputPreview.endRun(run.token)
            PerformanceHistory.endRun(run.token)
            NativeBridge.releaseRun(run.token)
            main.post {
                if (job !== run) return@post
                job = null
                if (destroyed) return@post // A late completion must not overwrite a replacement service.
                if (ServerStatus.current.phase != "error") {
                    publish(ServerStatus("stopped", "点击启动可重新开启服务", 0, false, 0, 0.0))
                }
                finishService()
            }
        }
    }

    private fun reportFailure(run: RunJob, error: Throwable) {
        main.post {
            if (job === run && !destroyed && !run.cancelled.get()) {
                publish(ServerStatus("error", message(error), 0, false, 0, 0.0))
            }
        }
    }

    private fun stopRun() {
        val run = job
        if (run == null) {
            finishService()
            return
        }
        run.cancelled.set(true)
        InputPreview.endRun(run.token)
        PerformanceHistory.endRun(run.token)
        NativeBridge.requestStop(run.token)
        publish(ServerStatus.current.copy(phase = "stopping", detail = "等待当前任务结束并释放模型",
            connected = false, listeningTransport = 0))
    }

    private fun publish(status: ServerStatus) {
        ServerStatus.current = status
        if (foreground && !destroyed) {
            requireNotNull(getSystemService(NotificationManager::class.java))
                .notify(NOTIFICATION, notification(status.title()))
        }
    }

    private fun finishService() {
        wakeLock?.let { if (it.isHeld) it.release() }
        if (foreground) stopForeground(STOP_FOREGROUND_REMOVE)
        foreground = false
        stopSelf()
    }

    private fun notification(text: String): Notification {
        val pendingFlags = PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), pendingFlags)
        val stop = PendingIntent.getService(this, 1,
            Intent(this, InferenceService::class.java).setAction(STOP), pendingFlags)
        return Notification.Builder(this, CHANNEL)
            .setSmallIcon(R.drawable.ic_notification).setContentTitle("OPIF · Cinque v3")
            .setContentText(text).setContentIntent(open).setOngoing(true).setOnlyAlertOnce(true)
            .setCategory(Notification.CATEGORY_SERVICE)
            .addAction(Notification.Action.Builder(null, "停止", stop).build()).build()
    }

    override fun onDestroy() {
        destroyed = true
        hotspotCallback?.let { getSystemService(ConnectivityManager::class.java).unregisterNetworkCallback(it) }
        hotspotCallback = null
        job?.let {
            it.cancelled.set(true)
            InputPreview.endRun(it.token)
            PerformanceHistory.endRun(it.token)
            NativeBridge.requestStop(it.token)
        }
        wakeLock?.let { if (it.isHeld) it.release() }
        worker.shutdown() // Drain native execution cooperatively; never free live buffers.
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun requestHotspot() {
        if (hotspotCallback != null) return
        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.NEARBY_WIFI_DEVICES) != PackageManager.PERMISSION_GRANTED) return
        val file = File(filesDir, "hotspot.json")
        if (!file.isFile) return
        try {
            val config = JSONObject(file.readText())
            val ssid = config.getString("ssid")
            val passphrase = config.getString("passphrase")
            require(ssid.isNotBlank() && passphrase.length in 8..63)
            val request = NetworkRequest.Builder()
                .addTransportType(NetworkCapabilities.TRANSPORT_WIFI)
                .removeCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                .setNetworkSpecifier(WifiNetworkSpecifier.Builder().setSsid(ssid)
                    .setWpa2Passphrase(passphrase).build()).build()
            val manager = requireNotNull(getSystemService(ConnectivityManager::class.java))
            val callback = object : ConnectivityManager.NetworkCallback() {
                override fun onAvailable(network: Network) {
                    Log.i("OpenPilotNPU", "C3 local Wi-Fi available: " + manager.getLinkProperties(network)?.interfaceName)
                }
                override fun onLost(network: Network) { Log.w("OpenPilotNPU", "C3 local Wi-Fi lost") }
                override fun onUnavailable() { Log.w("OpenPilotNPU", "C3 local Wi-Fi unavailable") }
            }
            manager.requestNetwork(request, callback)
            hotspotCallback = callback
            Log.i("OpenPilotNPU", "C3 local Wi-Fi requested")
        } catch (error: Exception) {
            Log.e("OpenPilotNPU", "C3 local Wi-Fi request failed", error)
        }
    }

    companion object {
        const val START = "com.example.openpilotinference.android.START"
        const val STOP = "com.example.openpilotinference.android.STOP"
        private const val CHANNEL = "inference"
        private const val NOTIFICATION = 1
        private fun message(error: Throwable) = error.message ?: error.javaClass.simpleName
    }
    override fun dump(fd: FileDescriptor?, writer: PrintWriter?, args: Array<out String>?) {
        writer?.println("OPIF_PREVIEW " + InputPreview.diagnostic())
    }

}
