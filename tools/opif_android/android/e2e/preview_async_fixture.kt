package com.example.openpilotinference.android
import java.net.DatagramSocket
import java.net.DatagramPacket
import java.net.InetAddress
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.io.File

private fun route(frame:Int):ByteArray {
 val b=ByteBuffer.allocate(672).order(ByteOrder.LITTLE_ENDIAN)
 b.put("SPR1".toByteArray());b.put(1);b.put(1);b.putShort(3)
 b.putLong(frame+1L);b.putLong(77);b.putLong(1);b.putLong(0);b.putLong(1_000_000_000L+frame*50_000_000L)
 b.putInt(frame);b.putInt(frame);b.putFloat(40f);b.putFloat(1.22f);b.putFloat(1f);b.putShort(160);b.putShort(33)
 listOf(256f,910f,0f,47.6f,0f,910f,1f,0f,0f,256f,455f,0f,151.8f,0f,455f,1f,0f,0f).forEach{b.putFloat(it)}
 for(i in 0..32){b.putFloat(10f+i*2f);b.putFloat(i*i*.002f);b.putFloat(0f)}
 repeat(33){b.putFloat(0f)}
 return b.array()
}
fun main(args:Array<String>){
 val owner=InputPreview.open(true);InputPreview.beginRun(1)
 val socket=DatagramSocket();val destination=InetAddress.getByName("127.0.0.1")
 val packed=ByteArray(393216);val begin=System.nanoTime();var routed=0;var offered=0
 var current:InputPreview.Frame?=null;var matched=0;var lastPair=-1L;var lastSeq=0L;var reversed=false
 val events=StringBuilder();var mismatch=false
 try{
  while((System.nanoTime()-begin)/1e6<2300){
   val ms=(System.nanoTime()-begin)/1e6
   while(routed<40&&ms>=routed*50){val data=route(routed);socket.send(DatagramPacket(data,data.size,destination,5556));routed++}
   while(offered<20&&ms>=offered*100+75){val frame=offered*2;InputPreview.offer(1,packed,frame+1L,77,1,1_000_000_000L+frame*50_000_000L);offered++}
   InputPreview.take(owner)?.let{val old=current;current=it;InputPreview.release(old)}
   val path=InputPreview.pathFor(current)
   if(path!=null&&current!=null&&path.publishSeq!=lastPair){
    val f=current!!;val exact=path.eofNs==f.eofNs&&path.sessionId==f.sessionId&&path.epoch==f.epoch
    mismatch=mismatch||!exact;reversed=reversed||path.publishSeq<lastSeq;lastSeq=path.publishSeq;lastPair=path.publishSeq;matched++
    // Simulated Canvas sink only; production recordDraw highwater/state is exercised.
    InputPreview.recordDraw(f,path)
    events.append("{\"ms\":$ms,\"publish_seq\":${path.publishSeq},\"request\":${f.requestId},\"eof_ns\":${f.eofNs},\"exact\":$exact}\n")
   }
   Thread.sleep(5)
  }
  val passed=matched>=8&&!mismatch&&!reversed
  File(args[0],"events.jsonl").writeText(events.toString())
  File(args[0],"status.json").writeText(InputPreview.diagnostic())
  val result="{\"passed\":$passed,\"matched_pairs\":$matched,\"route20hz\":$routed,\"input10hz\":$offered,\"input_completion_delay_ms\":75,\"metadata_mismatch\":$mismatch,\"publication_reversed\":$reversed,\"fixture\":\"real UDP and production InputPreview; Android/JNI synthetic substitutes\"}"
  File(args[0],"result.json").writeText(result+"\n");println(result)
 }finally{socket.close();InputPreview.release(current);InputPreview.close(owner);InputPreview.endRun(1)}
}
