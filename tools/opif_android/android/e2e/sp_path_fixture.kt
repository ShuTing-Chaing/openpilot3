package com.example.openpilotinference.android
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.io.File
// Host UDP->production decoder/matcher/projection E2E; Android canvas is not exercised.
fun main(args: Array<String>) {
 val socket=DatagramSocket(0); println(socket.localPort);System.out.flush()
 val buf=ByteArray(1201);val packet=DatagramPacket(buf,buf.size);socket.soTimeout=5000;socket.receive(packet);socket.close()
 val now=1_000_000_000L
 val route=SpPathProtocol.decode(buf.copyOf(packet.length),now) ?: error("valid fixture rejected")
 check(route.matches(77L,1L,12L,999L,now))
 check(!route.matches(78L,1L,12L,999L,now));check(!route.matches(77L,2L,12L,999L,now))
 check(!route.matches(77L,1L,13L,999L,now));check(!route.matches(77L,1L,12L,1000L,now))
 check(!route.matches(77L,1L,12L,999L,now+300_000_000L))
 val bad=buf.copyOf(packet.length);bad[4]=99;check(SpPathProtocol.decode(bad,now)==null)
 val nan=buf.copyOf(packet.length);nan[147]=0x7f;nan[146]=0xc0.toByte();check(SpPathProtocol.decode(nan,now)==null)
 val polys=(0..1).map{route.polygon(it)};check(polys.all{it.size>=8 && it.all{v->v.isFinite()}})
 val paths=polys.mapIndexed{cam,points->"<polygon fill='#0df87a' opacity='.4' points='"+points.asList().chunked(2).joinToString(" "){"${it[0]+cam*512},${it[1]}"}+"'/>"}.joinToString("")
 File(args[0]).writeText("<svg xmlns='http://www.w3.org/2000/svg' width='1024' height='256' viewBox='0 0 1024 256'><rect width='1024' height='256' fill='#161d28'/>$paths</svg>")
 println("{\"passed\":true,\"rejected_cases\":7,\"source\":\"synthetic UDP frame metadata; production Kotlin geometry\",\"polygon_points\":[${polys[0].size/2},${polys[1].size/2}]}")
}
