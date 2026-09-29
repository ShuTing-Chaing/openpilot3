package com.example.openpilotinference.android

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Shader
import android.widget.ImageView
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

/** Overlay is separate from the bitmap so expiry can remove it without a new image. */
internal class SpPreviewView(context: Context) : ImageView(context) {
    private var frame: InputPreview.Frame? = null
    private var route: SpPath? = null
    private val paint=Paint(Paint.ANTI_ALIAS_FLAG)
    fun routeFor(value: InputPreview.Frame?, path: SpPath?) { frame=value;route=path;invalidate() }
    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val image=frame ?: return;val path=route ?: return
        if (!path.matches(image.sessionId,image.epoch,image.requestId,image.eofNs,System.nanoTime())) return
        val scale=min(width/1024f,height/256f)
        canvas.save();canvas.translate((width-1024*scale)/2,(height-256*scale)/2);canvas.scale(scale,scale)
        var drawn=0
        for (camera in 0..1) {
            val pts=path.polygon(camera);if(pts.size<8)continue
            canvas.save();canvas.translate(camera*512f,0f);canvas.clipRect(0f,0f,512f,256f)
            val polygon=Path();polygon.moveTo(pts[0],pts[1]);for(i in 2 until pts.size step 2)polygon.lineTo(pts[i],pts[i+1]);polygon.close()
            val colors=if(path.flags and 4 != 0) {
                IntArray(3){i -> accelerationColor(path.acceleration[min(32,i*16)], if(i==2)0 else if(i==1)89 else 102)}
            } else {
                val blend=if(path.flags and 8 == 0)1f else path.blend
                IntArray(3){i ->
                    val green=if(i==0)intArrayOf(13,248,122) else intArrayOf(114,255,92)
                    Color.argb(if(i==2)0 else if(i==1)89 else 102,
                        (242+(green[0]-242)*blend).toInt(),(242+(green[1]-242)*blend).toInt(),(242+(green[2]-242)*blend).toInt())
                }
            }
            paint.shader=LinearGradient(0f,256f,0f,0f,colors,floatArrayOf(0f,.5f,1f),Shader.TileMode.CLAMP)
            canvas.drawPath(polygon,paint);drawn++;paint.shader=null;canvas.restore()
        }
        canvas.restore()
        if(drawn>0)InputPreview.recordDraw(image,path)
    }
    private fun accelerationColor(a: Float,alpha:Int): Int {
        val hue=max(0f,min(120f,60f+a*35f));val saturation=min(abs(a*1.5f),1f);val light=.95f+(.62f-.95f)*saturation
        // Convert SP HSL to HSV for Android Color, preserving its acceleration semantics.
        val value=light+saturation*min(light,1-light)
        val hsvS=if(value<=0)0f else 2*(1-light/value)
        return Color.HSVToColor(alpha,floatArrayOf(hue,hsvS,value))
    }
}
