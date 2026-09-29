package com.example.openpilotinference.android
internal object NativeBridge {
 fun setPreviewEnabled(enabled:Boolean){}
 fun renderPreview(packed:ByteArray,pixels:IntArray){pixels.fill(0xff161d28.toInt())}
}
