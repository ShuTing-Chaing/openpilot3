package com.example.openpilotinference.android

import android.graphics.Bitmap
import android.os.Process
import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.SocketTimeoutException
import java.util.ArrayDeque
import java.util.concurrent.Executors

/** Bounded display-only copy. Six preallocated packed slots, two owned bitmaps. */
internal object InputPreview {
    const val WIDTH=1024; const val HEIGHT=256
    private const val PACKED_BYTES=2*6*128*256
    data class Frame(val bitmap:Bitmap,val requestId:Long,val generation:Long,
        val sessionId:Long,val epoch:Long,val eofNs:Long)
    private class Slot { val packed=ByteArray(PACKED_BYTES);var busy=false }
    private data class Input(val slot:Slot,val requestId:Long,val generation:Long,
        val sessionId:Long,val epoch:Long,val eofNs:Long,val receivedNs:Long)
    private val lock=Any()
    private val slots by lazy { List(6){Slot()} }
    private val history=ArrayDeque<Input>(6)
    private val routes=ArrayDeque<SpPath>(12)
    private val free=ArrayDeque<Bitmap>(2)
    private val pixels by lazy { IntArray(WIDTH*HEIGHT) }
    private val worker=Executors.newSingleThreadExecutor { task ->
        Thread({Process.setThreadPriority(Process.THREAD_PRIORITY_BACKGROUND);task.run()},"opif-preview").apply{isDaemon=true}
    }
    private var allocated=0;private var scheduled=false;private var ready:Frame?=null
    private var nextOwner=0L;private var owner=0L;private var run=0L;private var generation=0L
    private var session=0L;private var epoch=0L;private var enabled=false;private var nativeDisablePending=false
    private var lastRenderedRequest=0L;private var lastRenderedSession=0L
    private var lastRenderedEof=0L
    private var latestRouteSeq=0L
    private var socket:DatagramSocket?=null
    @Volatile var error:String?=null;private set
    @Volatile var routeError:String?=null;private set
    @Volatile var routePackets=0L;private set
    @Volatile var rejectedPackets=0L;private set
    private var drawCount=0L;private var lastDrawSeq=0L;private var lastDrawSession=0L
    private var lastDrawEpoch=0L;private var lastDrawEof=0L;private var lastDrawRequest=0L
    private var lastDrawNs=0L;private var lastDrawExpiry=0L;private var lastDrawSource=0
    fun recordDraw(frame:Frame,path:SpPath)=synchronized(lock) {
        val now=System.nanoTime()
        if(frame.generation!=generation||!mayDisplayLocked(path)||!path.matches(frame.sessionId,frame.epoch,frame.requestId,frame.eofNs,now))return@synchronized
        drawCount++;lastDrawSeq=path.publishSeq;lastDrawSession=path.sessionId;lastDrawEpoch=path.epoch
        lastDrawEof=path.eofNs;lastDrawRequest=frame.requestId;lastDrawNs=now;lastDrawExpiry=path.expiresNs;lastDrawSource=path.source
    }
    /** Read-only Android service dumpsys; no socket/control/config mutation. */
    fun diagnostic():String=synchronized(lock) {
        JSONObject().apply {
            put("schema","opif-preview-status-v1");put("enabled",enabled);put("route_packets",routePackets)
            put("rejected_packets",rejectedPackets);put("draw_count",drawCount);put("last_draw_publish_seq",lastDrawSeq)
            put("last_draw_session_id",java.lang.Long.toUnsignedString(lastDrawSession));put("last_draw_epoch",lastDrawEpoch)
            put("last_draw_eof_ns",lastDrawEof);put("last_draw_request_id",lastDrawRequest);put("last_draw_source",lastDrawSource)
            put("last_draw_phone_ns",lastDrawNs);put("phone_now_ns",System.nanoTime())
            put("last_draw_receipt_ttl_valid",lastDrawExpiry>System.nanoTime());put("history_slots",history.size)
            put("route_slots",routes.size);put("bitmap_allocated",allocated);put("generation",generation)
            put("route_error",routeError?:JSONObject.NULL);put("preview_error",error?:JSONObject.NULL)
        }.toString()
    }

    fun open(wanted:Boolean):Long {
        val token=synchronized(lock){owner=++nextOwner;enabled=wanted;error=null;nativeDisablePending=false;invalidateLocked();owner}
        enableNative(wanted);configureRouteSocket();return token
    }
    fun setEnabled(token:Long,wanted:Boolean) {
        synchronized(lock){if(token!=owner||token==0L)return;enabled=wanted;error=null;nativeDisablePending=false;invalidateLocked()}
        enableNative(wanted);configureRouteSocket()
    }
    fun close(token:Long) {
        synchronized(lock){if(token!=owner||token==0L)return;owner=0L;enabled=false;nativeDisablePending=false;invalidateLocked()}
        enableNative(false);configureRouteSocket()
    }
    private fun enableNative(wanted:Boolean) {
        try{NativeBridge.setPreviewEnabled(wanted)}catch(failure:LinkageError){synchronized(lock){enabled=false;error=failure.message;invalidateLocked()}}
    }
    fun syncNativeFailure(token:Long) {
        val disable=synchronized(lock){if(token!=owner||token==0L||enabled||!nativeDisablePending)false else{nativeDisablePending=false;true}}
        if(disable){enableNative(false);configureRouteSocket()}
    }
    fun beginRun(token:Long)=synchronized(lock){run=token;invalidateLocked()}
    fun resetSession(token:Long)=synchronized(lock){if(run==token)invalidateLocked()}
    fun endRun(token:Long)=synchronized(lock){if(run==token){run=0;invalidateLocked()}}
    private fun invalidateLocked() {
        generation++;history.clear();routes.clear();session=0;epoch=0
        lastRenderedRequest=0;lastRenderedSession=0;lastRenderedEof=0;latestRouteSeq=0
        ready?.let{free.addLast(it.bitmap)};ready=null
    }
    /** Native passes reusable staging storage on its BACKGROUND telemetry thread. */
    fun offer(token:Long,packed:ByteArray,requestId:Long,sessionId:Long,stateEpoch:Long,eofNs:Long) = synchronized(lock) {
        if(run!=token||owner==0L||!enabled||packed.size!=PACKED_BYTES||sessionId==0L||stateEpoch<=0||eofNs<=0)return@synchronized
        if(session!=sessionId||epoch!=stateEpoch) {
            history.clear();routes.removeIf{it.sessionId!=sessionId||it.epoch!=stateEpoch}
            session=sessionId;epoch=stateEpoch;lastRenderedRequest=0;lastRenderedSession=0;lastRenderedEof=0
            latestRouteSeq=routes.maxOfOrNull{it.publishSeq}?:0L
            // Old asynchronous bitmap completions cannot enter this session.
            generation++;ready?.let{free.addLast(it.bitmap)};ready=null
        }
        val slot=slots.firstOrNull{!it.busy&&history.none{input->input.slot===it}}
            ?: history.firstOrNull{!it.slot.busy}?.slot ?: return@synchronized
        history.removeIf{it.slot===slot}
        packed.copyInto(slot.packed)
        history.addLast(Input(slot,requestId,generation,sessionId,stateEpoch,eofNs,System.nanoTime()))
        scheduleLocked()
    }
    private fun mayDisplayLocked(path:SpPath):Boolean =
        path.sessionId!=lastDrawSession || path.epoch!=lastDrawEpoch || path.publishSeq>=lastDrawSeq
    private fun routeLocked(input:Input,now:Long):SpPath? = routes.lastOrNull{
        mayDisplayLocked(it) && it.matches(input.sessionId,input.epoch,input.requestId,input.eofNs,now)
    }
    fun pathFor(frame:Frame?):SpPath? = synchronized(lock) {
        if(frame==null||frame.generation!=generation)return@synchronized null
        val now=System.nanoTime();routes.removeIf{it.expiresNs<=now}
        routes.lastOrNull{mayDisplayLocked(it) && it.matches(frame.sessionId,frame.epoch,frame.requestId,frame.eofNs,now)}
    }
    private fun scheduleLocked() {
        if(scheduled||ready!=null||owner==0L||!enabled||(free.isEmpty()&&allocated>=2))return
        val now=System.nanoTime();routes.removeIf{it.expiresNs<=now}
        // Route and image delivery have independent phase; find the newest valid
        // matching pair, not the global newest route (which may precede its image).
        val input=history.mapNotNull{image->routeLocked(image,now)?.let{image to it.publishSeq}}
            .maxByOrNull{it.second}?.first ?: history.lastOrNull() ?: return
        if(input.requestId==lastRenderedRequest&&input.sessionId==lastRenderedSession&&input.eofNs==lastRenderedEof)return
        input.slot.busy=true;scheduled=true
        worker.execute{render(input)}
    }
    private fun render(input:Input) {
        var bitmap=synchronized(lock){free.pollFirst().also{if(it==null)allocated++}}
        var failure:Throwable?=null
        try {
            if(bitmap==null)bitmap=Bitmap.createBitmap(WIDTH,HEIGHT,Bitmap.Config.ARGB_8888)
            NativeBridge.renderPreview(input.slot.packed,pixels)
            bitmap.setPixels(pixels,0,WIDTH,0,0,WIDTH,HEIGHT)
        } catch(problem:RuntimeException){failure=problem}catch(problem:LinkageError){failure=problem}catch(problem:OutOfMemoryError){failure=problem}
        synchronized(lock) {
            input.slot.busy=false;scheduled=false
            if(failure==null&&input.generation==generation&&owner!=0L&&enabled) {
                ready=Frame(requireNotNull(bitmap),input.requestId,generation,input.sessionId,input.epoch,input.eofNs)
                lastRenderedRequest=input.requestId;lastRenderedSession=input.sessionId;lastRenderedEof=input.eofNs
            } else {
                if(bitmap==null)allocated-- else free.addLast(bitmap)
                if(failure!=null&&input.generation==generation){error=failure.message?:failure.javaClass.simpleName;enabled=false;nativeDisablePending=true;invalidateLocked()}
            }
            scheduleLocked()
        }
    }
    fun generation(token:Long):Long=synchronized(lock){if(token==owner)generation else -1L}
    fun take(token:Long):Frame?=synchronized(lock){
        if(token!=owner||!enabled)return@synchronized null
        val result=ready?:return@synchronized null;ready=null;scheduleLocked();result
    }
    fun release(frame:Frame?){if(frame!=null)synchronized(lock){free.addLast(frame.bitmap);scheduleLocked()}}

    private fun configureRouteSocket() {
        synchronized(lock) {
            if(!enabled||owner==0L){socket?.close();socket=null;return}
            if(socket!=null)return
            routeError=null
            val receiver=try{DatagramSocket(SpPathProtocol.PORT).apply{soTimeout=200;receiveBufferSize=16*1024}}
                catch(failure:Exception){routeError=failure.message;return}
            socket=receiver
            Thread({
                Process.setThreadPriority(Process.THREAD_PRIORITY_BACKGROUND)
                val bytes=ByteArray(1201)
                while(!receiver.isClosed) {
                    try {
                        val packet=DatagramPacket(bytes,bytes.size);receiver.receive(packet)
                        val route=SpPathProtocol.decode(bytes.copyOf(packet.length),System.nanoTime())
                        synchronized(lock) {
                            if(socket!==receiver||!enabled)return@synchronized
                            if(route==null||(session!=0L&&(route.sessionId!=session||route.epoch!=epoch)))rejectedPackets++
                            else {
                                val newer=route.publishSeq>latestRouteSeq
                                if(newer){latestRouteSeq=route.publishSeq;if(routes.size>=12)routes.removeFirst();routes.addLast(route);routePackets++;scheduleLocked()}else rejectedPackets++
                            }
                        }
                    } catch(_:SocketTimeoutException){}catch(failure:Exception){if(!receiver.isClosed)routeError=failure.message;break}
                }
            },"opif-sp-route").apply{isDaemon=true;start()}
        }
    }
}
