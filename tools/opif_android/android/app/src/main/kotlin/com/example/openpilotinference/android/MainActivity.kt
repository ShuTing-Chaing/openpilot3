package com.example.openpilotinference.android

import android.Manifest
import android.app.Activity
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.content.pm.PackageManager
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.view.Gravity
import android.view.View
import android.view.WindowInsets
import android.view.WindowManager
import android.widget.Button
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Switch
import android.widget.Toast
import java.net.Inet4Address
import java.net.NetworkInterface
import java.util.Collections
import java.util.ArrayDeque
import java.util.Locale
import kotlin.math.roundToInt

class MainActivity : Activity() {
    private val main = Handler(Looper.getMainLooper())
    private lateinit var status: TextView
    private lateinit var detail: TextView
    private lateinit var address: TextView
    private lateinit var latency: TextView
    private lateinit var frames: TextView
    private lateinit var networkNote: TextView
    private lateinit var transportChoices: RadioGroup
    private lateinit var dot: View
    private lateinit var toggle: Button
    private lateinit var copy: Button
    private lateinit var progress: ProgressBar
    private lateinit var previewSwitch: Switch
    private lateinit var previewImage: SpPreviewView
    private lateinit var previewEmpty: TextView
    private lateinit var previewInfo: TextView
    private lateinit var performanceQuantiles: TextView
    private lateinit var performanceInfo: TextView
    private lateinit var performanceLegend: TextView
    private lateinit var performancePlot: PerformancePlot
    private var previewEnabled = true
    private var listenTransport = ListenTransport.BOTH
    private var previewOwner = 0L
    private var previewFrame: InputPreview.Frame? = null
    private val previewTimes = ArrayDeque<Long>(24)
    private var nextAddressUpdate = 0L
    private var copyAddress = ""
    private var firstStart = true
    private val refresh = object : Runnable {
        override fun run() {
            render()
            main.postDelayed(this, 500)
        }
    }
    private val previewRefresh = object : Runnable {
        override fun run() {
            renderPreview()
            main.postDelayed(this, 100)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        previewEnabled = getPreferences(MODE_PRIVATE).getBoolean(PREVIEW_ENABLED, true)
        listenTransport = ListenTransport.load(this)
        applyTransportIntent(intent)
        applyPreviewIntent(intent)
        buildUI()
        // Bundle state survives process death; the native server does not.
        val autoStart = savedInstanceState == null || !openedInThisProcess
        openedInThisProcess = true
        if (autoStart) startServer()
        val missingPermissions = mutableListOf<String>()
        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED &&
            !getPreferences(MODE_PRIVATE).getBoolean("notificationAsked", false)
        ) {
            getPreferences(MODE_PRIVATE).edit().putBoolean("notificationAsked", true).apply()
            missingPermissions.add(Manifest.permission.POST_NOTIFICATIONS)
        }
        if (Build.VERSION.SDK_INT >= 33 &&
            java.io.File(filesDir, "hotspot.json").isFile &&
            checkSelfPermission(Manifest.permission.NEARBY_WIFI_DEVICES) != PackageManager.PERMISSION_GRANTED) {
            missingPermissions.add(Manifest.permission.NEARBY_WIFI_DEVICES)
        }
        if (missingPermissions.isNotEmpty()) requestPermissions(missingPermissions.toTypedArray(), 2)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        applyPreviewIntent(intent)
        previewSwitch.isChecked = previewEnabled
        val previousTransport = listenTransport
        applyTransportIntent(intent)
        transportChoices.check(listenTransport.nativeValue)
        if (previousTransport != listenTransport && ServerStatus.current.active()) startServer()
        if (Intent.ACTION_MAIN == intent.action) startServer()
        render()
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == 2 && permissions.indices.any {
                permissions[it] == Manifest.permission.NEARBY_WIFI_DEVICES &&
                    grantResults.getOrNull(it) == PackageManager.PERMISSION_GRANTED
            }) startServer()
    }

    override fun onStart() {
        super.onStart()
        // Returning from the launcher starts a stopped server. Rotation's first
        // onStart preserves a deliberate stop in the current foreground visit.
        if (!firstStart && !ServerStatus.current.active()) startServer()
        firstStart = false
        previewOwner = InputPreview.open(previewEnabled)
        previewRefresh.run()
        refresh.run()
    }

    override fun onStop() {
        main.removeCallbacks(refresh)
        main.removeCallbacks(previewRefresh)
        InputPreview.close(previewOwner)
        previewOwner = 0L
        clearPreview()
        super.onStop()
    }

    private fun applyPreviewIntent(intent: Intent?) {
        if (intent?.hasExtra(PREVIEW_ENABLED) == true) {
            previewEnabled = intent.getBooleanExtra(PREVIEW_ENABLED, true)
            getPreferences(MODE_PRIVATE).edit().putBoolean(PREVIEW_ENABLED, previewEnabled).apply()
        }
    }

    private fun startServer() {
        try {
            startForegroundService(Intent(this, InferenceService::class.java).setAction(InferenceService.START))
        } catch (error: RuntimeException) {
            ServerStatus.current = ServerStatus("error", error.toString(), 0, false, 0, 0.0)
            render()
        }
    }

    private fun applyTransportIntent(intent: Intent?) {
        val selected = ListenTransport.fromKey(intent?.getStringExtra(ListenTransport.EXTRA)) ?: return
        listenTransport = selected
        selected.save(this)
        intent?.removeExtra(ListenTransport.EXTRA)
    }

    private fun buildUI() {
        val outer = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(BG)
            setOnApplyWindowInsetsListener { view, insets ->
                val safe = insets.getInsets(WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout())
                view.setPadding(safe.left, safe.top, safe.right, safe.bottom)
                insets
            }
        }
        val scroll = ScrollView(this).apply {
            isFillViewport = true
            clipToPadding = false
        }
        outer.addView(scroll, LinearLayout.LayoutParams(-1, -1))
        val body = column().apply { setPadding(dp(20), dp(16), dp(20), dp(24)) }
        scroll.addView(body, FrameLayout.LayoutParams(-1, -2))

        val heading = LinearLayout(this).apply { gravity = Gravity.CENTER_VERTICAL }
        val wordmark = text("OPIF", 15, MUTED).apply { letterSpacing = 0.18f }
        heading.addView(wordmark, LinearLayout.LayoutParams(0, -2, 1f))
        val badge = text("NPU ONLY", 11, GREEN).apply {
            setTypeface(Typeface.DEFAULT, Typeface.BOLD)
            letterSpacing = 0.08f
            setPadding(dp(12), dp(7), dp(12), dp(7))
            background = shape(Color.rgb(20, 44, 34), 20)
        }
        heading.addView(badge)
        body.addView(heading)
        space(body, 12)
        val title = text("Inference Server", 28, INK).apply {
            setTypeface(Typeface.DEFAULT, Typeface.BOLD)
            setLineSpacing(0f, 0.97f)
        }
        body.addView(title)
        val subtitle = text("Cinque v3 · comma Big Model", 15, MUTED).apply {
            setPadding(0, dp(6), 0, 0)
        }
        body.addView(subtitle)
        space(body, 16)

        val stateCard = card()
        val stateRow = LinearLayout(this).apply { gravity = Gravity.CENTER_VERTICAL }
        dot = View(this).apply { background = shape(MUTED, 6) }
        val dotLayout = LinearLayout.LayoutParams(dp(9), dp(9)).apply { marginEnd = dp(12) }
        stateRow.addView(dot, dotLayout)
        status = text("正在启动", 20, INK).apply { setTypeface(Typeface.DEFAULT, Typeface.BOLD) }
        stateRow.addView(status, LinearLayout.LayoutParams(0, -2, 1f))
        stateCard.addView(stateRow)
        detail = text("模型准备完成后自动开始监听", 13, MUTED).apply {
            setTextIsSelectable(true)
            setLineSpacing(dp(4).toFloat(), 1f)
            setPadding(0, dp(12), 0, 0)
        }
        stateCard.addView(detail)
        progress = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
            progressTintList = ColorStateList.valueOf(GREEN)
        }
        val progressLayout = LinearLayout.LayoutParams(-1, dp(4)).apply { topMargin = dp(18) }
        stateCard.addView(progress, progressLayout)
        body.addView(stateCard)
        space(body, 12)

        val previewCard = card()
        previewSwitch = Switch(this).apply {
            text = "视频预览"
            textSize = 16f
            setTextColor(INK)
            isChecked = previewEnabled
            setPadding(0, 0, 0, dp(6))
            setOnCheckedChangeListener { _, checked ->
                previewEnabled = checked
                getPreferences(MODE_PRIVATE).edit().putBoolean(PREVIEW_ENABLED, checked).apply()
                if (previewOwner != 0L) InputPreview.setEnabled(previewOwner, checked)
                clearPreview()
                renderPreview()
            }
        }
        previewCard.addView(previewSwitch, LinearLayout.LayoutParams(-1, -2))
        previewCard.addView(text("模型输入 + SP 同帧路径 · 左：窄摄 / 右：广摄 · 最多 10 fps", 11, MUTED))
        val previewArea = object : FrameLayout(this) {
            override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
                super.onMeasure(widthMeasureSpec,
                    View.MeasureSpec.makeMeasureSpec(View.MeasureSpec.getSize(widthMeasureSpec) / 4, View.MeasureSpec.EXACTLY))
            }
        }.apply { setBackgroundColor(Color.BLACK) }
        previewImage = SpPreviewView(this).apply {
            scaleType = ImageView.ScaleType.FIT_CENTER
            // Software composition finishes reading the old bitmap on the UI
            // thread, before it is returned to the worker's two-bitmap pool.
            setLayerType(View.LAYER_TYPE_SOFTWARE, null)
            contentDescription = "双摄模型输入，左侧窄摄，右侧广摄"
        }
        previewArea.addView(previewImage, FrameLayout.LayoutParams(-1, -1))
        previewEmpty = text("等待客户端视频输入", 12, MUTED).apply { gravity = Gravity.CENTER }
        previewArea.addView(previewEmpty, FrameLayout.LayoutParams(-1, -1))
        previewCard.addView(previewArea, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(10) })
        previewInfo = text("等待输入", 11, MUTED).apply { setPadding(0, dp(8), 0, 0) }
        previewCard.addView(previewInfo)
        body.addView(previewCard)
        space(body, 12)

        val performanceCard = card()
        performanceCard.addView(text("推理性能 · 最近最多 256 帧", 14, INK))
        performanceQuantiles = text("p50 —    p99 —", 21, GREEN).apply { setPadding(0, dp(10), 0, dp(6)) }
        performanceCard.addView(performanceQuantiles)
        performanceInfo = text("等待完成帧 · 0.0 FPS", 12, MUTED)
        performanceCard.addView(performanceInfo)
        performancePlot = PerformancePlot(this)
        performanceCard.addView(performancePlot, LinearLayout.LayoutParams(-1, dp(144)).apply { topMargin = dp(8) })
        performanceLegend = text("上：推理耗时 ms · 下：完成 FPS · FPS 保留最近 10 秒", 10, MUTED)
        performanceCard.addView(performanceLegend)
        body.addView(performanceCard)
        space(body, 12)

        val endpointCard = card()
        endpointCard.addView(text("监听协议", 12, MUTED))
        transportChoices = RadioGroup(this).apply {
            orientation = RadioGroup.HORIZONTAL
            for (mode in ListenTransport.values()) {
                addView(RadioButton(this@MainActivity).apply {
                    id = mode.nativeValue
                    text = if (mode == ListenTransport.BOTH) "同时" else mode.label
                    textSize = 14f
                    setTextColor(INK)
                    buttonTintList = ColorStateList(arrayOf(intArrayOf(android.R.attr.state_checked), intArrayOf()),
                        intArrayOf(GREEN, MUTED))
                    minHeight = dp(48)
                }, RadioGroup.LayoutParams(0, -2, 1f))
            }
            check(listenTransport.nativeValue)
            setOnCheckedChangeListener { _, checkedId ->
                val selected = ListenTransport.fromNative(checkedId) ?: return@setOnCheckedChangeListener
                if (selected == listenTransport) return@setOnCheckedChangeListener
                listenTransport = selected
                selected.save(this@MainActivity)
                if (ServerStatus.current.active()) startServer()
                render()
            }
        }
        endpointCard.addView(transportChoices)
        endpointCard.addView(text("切换会断开当前客户端，模型保持加载", 11, MUTED))
        space(endpointCard, 16)
        endpointCard.addView(text("连接地址", 12, MUTED))
        address = text("正在获取 IP…", 20, INK).apply {
            typeface = Typeface.MONOSPACE
            setTextIsSelectable(true)
            setPadding(0, dp(12), 0, dp(8))
        }
        endpointCard.addView(address)
        networkNote = text("${listenTransport.label} 5555 · 启动完成后可连接", 12, MUTED)
        endpointCard.addView(networkNote)
        copy = button("复制地址", false)
        val copyLayout = LinearLayout.LayoutParams(-1, dp(44)).apply { topMargin = dp(16) }
        endpointCard.addView(copy, copyLayout)
        copy.setOnClickListener {
            getSystemService(ClipboardManager::class.java)
                ?.setPrimaryClip(ClipData.newPlainText("OPIF", copyAddress))
            Toast.makeText(this, "已复制连接地址", Toast.LENGTH_SHORT).show()
        }
        body.addView(endpointCard)
        space(body, 12)

        val metrics = LinearLayout(this)
        val left = card()
        val right = card()
        left.addView(text("最近推理耗时", 12, MUTED))
        latency = text("—", 28, INK).apply { setPadding(0, dp(10), 0, 0) }
        left.addView(latency)
        right.addView(text("已完成帧数", 12, MUTED))
        frames = text("0", 28, INK).apply { setPadding(0, dp(10), 0, 0) }
        right.addView(frames)
        val half = LinearLayout.LayoutParams(0, -1, 1f).apply { marginEnd = dp(12) }
        metrics.addView(left, half)
        metrics.addView(right, LinearLayout.LayoutParams(0, -1, 1f))
        body.addView(metrics, LinearLayout.LayoutParams(-1, -2))
        space(body, 28)

        toggle = button("停止服务", true)
        body.addView(toggle, LinearLayout.LayoutParams(-1, dp(56)))
        toggle.setOnClickListener {
            if (ServerStatus.current.active()) {
                startService(Intent(this, InferenceService::class.java).setAction(InferenceService.STOP))
            } else {
                startServer()
            }
        }
        val footer = text("打开即启动 · 模型仅使用 NPU\n后台运行时可从通知栏停止", 12, MUTED).apply {
            gravity = Gravity.CENTER
            setLineSpacing(dp(5).toFloat(), 1f)
            setPadding(0, dp(20), 0, 0)
        }
        body.addView(footer)
        setContentView(outer)
        outer.requestApplyInsets()
    }

    private fun render() {
        val current = ServerStatus.current
        val actualTransport = ListenTransport.fromNative(current.listeningTransport)
        val pendingTransport = current.ready() && actualTransport != listenTransport
        val visiblePhase = if (pendingTransport) "switching" else current.phase
        status.text = if (pendingTransport) "正在切换监听协议" else current.title()
        val color = when {
            current.phase == "error" -> RED
            current.ready() && !pendingTransport -> GREEN
            else -> MUTED
        }
        dot.background = shape(color, 6)
        detail.text = when (visiblePhase) {
            "loading" -> "正在加载 NPU 模型；首次启动或编译缓存失效时需要较长时间"
            "listening" -> "服务已就绪，可从 comma 连接下方地址"
            "connected" -> "正在接收客户端请求"
            "switching" -> "正在切换到 ${listenTransport.label}，客户端需要重新连接"
            "preparing" -> "${current.detail} · ${current.progress}%"
            else -> current.detail
        }
        detail.setTextColor(if (current.phase == "error") RED else MUTED)
        progress.visibility = if (current.phase == "preparing" || current.phase == "loading") View.VISIBLE else View.GONE
        progress.isIndeterminate = current.phase == "loading"
        progress.progress = current.progress
        frames.text = String.format(Locale.ROOT, "%,d", current.frames)
        latency.text = if (current.frames > 0) String.format(Locale.ROOT, "%.1f ms", current.inferenceMs) else "—"
        renderPerformance()
        toggle.text = when {
            current.phase == "stopping" -> "正在停止…"
            current.active() -> "停止服务"
            current.phase == "error" -> "重试启动"
            else -> "启动服务"
        }
        toggle.isEnabled = current.phase != "stopping"
        toggle.alpha = if (toggle.isEnabled) 1f else 0.5f
        networkNote.text = when {
            current.ready() && actualTransport == listenTransport -> "${listenTransport.label} 5555 · 服务已就绪"
            current.phase == "switching" || (current.ready() && actualTransport != listenTransport) ->
                "${listenTransport.label} 5555 · 正在切换"
            else -> "${listenTransport.label} 5555 · 启动完成后可连接"
        }
        for (index in 0 until transportChoices.childCount) {
            transportChoices.getChildAt(index).isEnabled = current.phase != "stopping"
        }
        if (SystemClock.elapsedRealtime() >= nextAddressUpdate) {
            nextAddressUpdate = SystemClock.elapsedRealtime() + 3000
            val addresses = addresses()
            copyAddress = addresses.joinToString("\n")
            address.text = if (addresses.isEmpty()) "未找到本地 IPv4 地址" else copyAddress
            copy.isEnabled = addresses.isNotEmpty()
        }
    }

    private fun clearPreview() {
        previewImage.setImageDrawable(null)
        previewImage.routeFor(null, null)
        val previous = previewFrame
        previewFrame = null
        InputPreview.release(previous)
        previewTimes.clear()
        previewEmpty.visibility = View.VISIBLE
    }

    private fun renderPreview() {
        if (previewOwner != 0L) {
            InputPreview.syncNativeFailure(previewOwner)
            val version = InputPreview.generation(previewOwner)
            if (previewFrame?.generation?.let { it != version } == true) clearPreview()
            val next = InputPreview.take(previewOwner)
            if (next != null) {
                if (next.generation != InputPreview.generation(previewOwner)) {
                    InputPreview.release(next)
                } else {
                    val previous = previewFrame
                    previewImage.setImageBitmap(next.bitmap)
                    previewFrame = next
                    previewEmpty.visibility = View.GONE
                    InputPreview.release(previous)
                    previewTimes.addLast(System.nanoTime())
                    while (previewTimes.size > 24) previewTimes.removeFirst()
                }
            }
        }
        val route = InputPreview.pathFor(previewFrame)
        previewImage.routeFor(previewFrame, route)
        val now = System.nanoTime()
        while (previewTimes.isNotEmpty() && now - previewTimes.first > 2_000_000_000L) previewTimes.removeFirst()
        val idle = previewTimes.isEmpty() || now - previewTimes.last > 1_000_000_000L
        val fps = if (!idle && previewTimes.size > 1)
            (previewTimes.size - 1) * 1e9 / (previewTimes.last - previewTimes.first) else 0.0
        previewEmpty.text = when {
            !previewEnabled -> "预览已关闭"
            InputPreview.error != null -> "预览暂不可用"
            else -> "等待客户端视频输入"
        }
        previewInfo.text = when {
            !previewEnabled -> "推理继续运行 · 预览已关闭"
            InputPreview.error != null -> "预览错误：${InputPreview.error}"
            previewFrame != null -> String.format(Locale.ROOT, "请求 %s · 预览 %.1f fps%s",
                java.lang.Long.toUnsignedString(previewFrame!!.requestId), fps, if (idle) " · 画面已过期，路径隐藏" else route?.let { " · ${it.sourceLabel} · 发布${it.publishSeq}" } ?: " · 等待同帧SP路径")
            else -> "等待输入 · 预览 0.0 fps"
        }
    }

    private fun renderPerformance() {
        val sample = PerformanceHistory.current
        performancePlot.snapshot = sample
        if (sample == null) {
            performanceQuantiles.text = "p50 —    p99 —"
            performanceInfo.text = "等待完成帧 · 0.0 FPS"
            performanceLegend.text = "上：推理耗时 ms · 下：完成 FPS · FPS 保留最近 10 秒"
            return
        }
        // JNI uses CLOCK_MONOTONIC, the same clock as System.nanoTime().
        val idle = System.nanoTime() - sample.completionNs > 1_000_000_000L
        performanceQuantiles.text = String.format(Locale.ROOT, "p50 %.1f    p99 %.1f ms", sample.p50, sample.p99)
        performanceInfo.text = String.format(Locale.ROOT, "均值 %.1f · 最近 %.1f ms\n%s %.1f FPS · %d 帧",
            sample.mean, sample.last, if (idle) "空闲" else "完成", if (idle) 0.0 else sample.fps, sample.count)
        performanceLegend.text = "上：推理耗时 ms · 下：FPS 最近 10 秒 · 自动刻度"
    }

    private fun addresses(): List<String> {
        val values = mutableListOf<String>()
        try {
            val networks = NetworkInterface.getNetworkInterfaces() ?: return values
            for (network in Collections.list(networks)) {
                if (!network.isUp || network.isLoopback) continue
                for (ip in Collections.list(network.inetAddresses)) {
                    if (ip is Inet4Address && !ip.isLoopbackAddress && !ip.isLinkLocalAddress) {
                        values.add("${ip.hostAddress}:5555")
                    }
                }
            }
        } catch (_: Exception) {
            // Network changes are retried on the next refresh.
        }
        return values.sorted()
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).roundToInt()

    private fun text(value: String, sp: Int, color: Int): TextView = TextView(this).apply {
        text = value
        textSize = sp.toFloat()
        setTextColor(color)
        includeFontPadding = false
    }

    private fun column(): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
    }

    private fun card(): LinearLayout = column().apply {
        setPadding(dp(20), dp(20), dp(20), dp(20))
        background = shape(CARD, 18)
    }

    private fun shape(color: Int, radius: Int): GradientDrawable = GradientDrawable().apply {
        setColor(color)
        cornerRadius = dp(radius).toFloat()
    }

    private fun button(title: String, primary: Boolean): Button = Button(this).apply {
        text = title
        isAllCaps = false
        textSize = 15f
        setTextColor(if (primary) BG else INK)
        setTypeface(Typeface.DEFAULT, Typeface.BOLD)
        backgroundTintList = null
        background = shape(if (primary) GREEN else Color.rgb(33, 41, 50), 12)
    }

    private fun space(parent: LinearLayout, height: Int) {
        parent.addView(View(this), LinearLayout.LayoutParams(1, dp(height)))
    }

    private companion object {
        const val PREVIEW_ENABLED = "preview_enabled"
        var openedInThisProcess = false
        val BG = Color.rgb(9, 12, 16)
        val CARD = Color.rgb(19, 24, 30)
        val INK = Color.rgb(240, 245, 248)
        val MUTED = Color.rgb(146, 158, 171)
        val GREEN = Color.rgb(128, 242, 188)
        val RED = Color.rgb(255, 151, 151)
    }
}
