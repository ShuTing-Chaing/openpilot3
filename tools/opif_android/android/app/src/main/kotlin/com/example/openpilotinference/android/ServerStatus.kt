package com.example.openpilotinference.android

internal data class ServerStatus(
    val phase: String,
    val detail: String,
    val progress: Int,
    val connected: Boolean,
    val frames: Long,
    val inferenceMs: Double,
    // Zero until the selected listeners have actually bound successfully.
    val listeningTransport: Int = 0,
) {
    fun active() = phase != "stopped" && phase != "error"
    fun ready() = phase == "listening" || phase == "connected"
    fun title() = when (phase) {
        "preparing" -> "正在准备模型"
        "loading" -> "正在加载 NPU"
        "listening" -> "等待客户端连接"
        "connected" -> "客户端已连接"
        "stopping" -> "正在停止"
        "switching" -> "正在切换监听协议"
        "error" -> "启动或运行失败"
        else -> "服务已停止"
    }

    companion object {
        @Volatile var current = ServerStatus("stopped", "打开应用后自动启动", 0, false, 0, 0.0)
    }
}
