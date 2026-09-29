package com.example.openpilotinference.android

import android.content.Context

internal enum class ListenTransport(val nativeValue: Int, val key: String, val label: String) {
    UDP(1, "udp", "UDP"),
    TCP(2, "tcp", "TCP"),
    BOTH(3, "both", "UDP / TCP");

    fun save(context: Context) {
        context.getSharedPreferences("server_settings", Context.MODE_PRIVATE)
            .edit().putString(EXTRA, key).apply()
    }

    companion object {
        const val EXTRA = "listen_transport"
        fun fromNative(value: Int) = values().firstOrNull { it.nativeValue == value }
        fun fromKey(value: String?) = values().firstOrNull { it.key == value }
        fun load(context: Context) = fromKey(context.getSharedPreferences("server_settings", Context.MODE_PRIVATE)
            .getString(EXTRA, BOTH.key)) ?: BOTH
    }
}
