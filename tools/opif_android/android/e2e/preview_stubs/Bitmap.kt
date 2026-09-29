package android.graphics
// Host integration fixture substitute: InputPreview scheduling runs unchanged.
class Bitmap {
 enum class Config { ARGB_8888 }
 fun setPixels(p:IntArray,o:Int,s:Int,x:Int,y:Int,w:Int,h:Int){}
 companion object { fun createBitmap(w:Int,h:Int,c:Config)=Bitmap() }
}
