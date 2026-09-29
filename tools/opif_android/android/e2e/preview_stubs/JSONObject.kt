package org.json
class JSONObject {
 private val values=linkedMapOf<String,Any?>()
 fun put(key:String,value:Any?):JSONObject {values[key]=value;return this}
 override fun toString()=values.entries.joinToString(",","{","}"){"\"${it.key}\":"+when(val v=it.value){is String->"\"$v\"";NULL,null->"null";else->v.toString()}}
 companion object {val NULL=Any()}
}
