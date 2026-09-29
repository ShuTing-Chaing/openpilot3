#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
#if defined(__aarch64__) && defined(__ARM_FEATURE_CRC32)
#include <arm_acle.h>
#endif
extern "C" uint32_t opif_crc32c(const uint8_t* data, size_t size) {
  uint32_t crc = 0xffffffffU;
#if defined(__aarch64__) && defined(__ARM_FEATURE_CRC32)
  while (size >= 8) { uint64_t chunk; std::memcpy(&chunk, data, 8); crc = __crc32cd(crc, chunk); data += 8; size -= 8; }
  while (size--) crc = __crc32cb(crc, *data++);
#else
  static const auto table = [] {
    std::array<uint32_t, 256> t{};
    for (uint32_t i = 0; i < 256; ++i) {
      uint32_t x = i;
      for (int k = 0; k < 8; ++k) x = (x >> 1) ^ ((x & 1) ? 0x82f63b78U : 0);
      t[i] = x;
    }
    return t;
  }();
  while (size--) crc = table[(crc ^ *data++) & 255] ^ (crc >> 8);
#endif
  return crc ^ 0xffffffffU;
}
extern "C" int opif_f32_finite(const uint8_t* data, size_t size) {
  if (size % 4) return 0;
  for (size_t i = 0; i < size; i += 4) {
    const uint32_t bits = uint32_t(data[i]) | uint32_t(data[i + 1]) << 8 | uint32_t(data[i + 2]) << 16 | uint32_t(data[i + 3]) << 24;
    if ((bits & 0x7f800000U) == 0x7f800000U) return 0;
  }
  return 1;
}

namespace {
void put16(uint8_t* p,uint16_t x){p[0]=x;p[1]=x>>8;}
void put32(uint8_t* p,uint32_t x){put16(p,uint16_t(x));put16(p+2,uint16_t(x>>16));}
void put64(uint8_t* p,uint64_t x){put32(p,uint32_t(x));put32(p+4,uint32_t(x>>32));}
}
extern "C" size_t opif_encode_tcp(uint8_t type,uint64_t session,uint64_t request,const uint8_t* body,size_t size,uint16_t maximum,uint8_t* out,size_t capacity){
  if(maximum<=40||maximum>65507||size>1048576)return 0;
  const size_t limit=maximum-40,count=size?(size+limit-1)/limit:1,total=size+44*count;
  if(count>65535||capacity<total)return 0;
  const uint32_t crc=opif_crc32c(body,size);size_t position=0;
  for(size_t i=0;i<count;++i){
    const size_t begin=i*limit,bytes=begin<size?((size-begin)<limit?size-begin:limit):0;
    uint8_t* p=out+position;put32(p,uint32_t(40+bytes));p+=4;
    std::memcpy(p,"OPIF",4);p[4]=1;p[5]=type;put16(p+6,0);put16(p+8,40);put16(p+10,uint16_t(bytes));
    put64(p+12,session);put64(p+20,request);put16(p+28,uint16_t(i));put16(p+30,uint16_t(count));put32(p+32,uint32_t(size));put32(p+36,crc);
    if(bytes)std::memcpy(p+40,body+begin,bytes);position+=44+bytes;
  }
  return position;
}

#include <deque>
#include <map>
#include <tuple>
#include <vector>
#include <stdexcept>
#include <string>
namespace {
uint16_t read16(const uint8_t* p){return uint16_t(p[0]) | uint16_t(p[1])<<8;}
uint32_t read32(const uint8_t* p){return uint32_t(read16(p)) | uint32_t(read16(p+2))<<16;}
uint64_t read64(const uint8_t* p){return uint64_t(read32(p)) | uint64_t(read32(p+4))<<32;}
using MessageKey=std::tuple<uint8_t,uint64_t,uint64_t>;
struct Assembly {uint32_t size=0,crc=0;uint16_t count=0;size_t received=0,bytes=0;std::vector<std::vector<uint8_t>> fragments;std::vector<bool> seen;};
struct Complete {MessageKey key;uint32_t crc;std::vector<uint8_t> body;};
struct Decoder {
  std::vector<uint8_t> raw;std::map<MessageKey,Assembly> partial;std::deque<Complete> complete;size_t reserved=0,complete_bytes=0;std::string error;
  void feed(const uint8_t* data,size_t size){
    if(raw.size()+size>2097152)throw std::runtime_error("OPIF receive buffer bound");
    raw.insert(raw.end(),data,data+size);size_t offset=0;
    while(raw.size()-offset>=4){
      const uint32_t length=read32(raw.data()+offset);
      if(length<40||length>1232)throw std::runtime_error("OPIF TCP packet length");
      if(raw.size()-offset<length+4)break;
      const uint8_t* p=raw.data()+offset+4;
      if(std::memcmp(p,"OPIF",4)||p[4]!=1||read16(p+6)||read16(p+8)!=40||read16(p+10)!=length-40)throw std::runtime_error("OPIF packet header");
      const uint16_t index=read16(p+28),count=read16(p+30);const uint32_t total=read32(p+32),crc=read32(p+36);const size_t bytes=length-40;
      if(!count||index>=count||total>1048576||count>2222||(total==0&&(count!=1||bytes!=0)))throw std::runtime_error("OPIF fragment metadata");
      MessageKey key{p[5],read64(p+12),read64(p+20)};
      auto it=partial.find(key);
      if(it==partial.end()){
        if(partial.size()>=64||reserved+total>4194304)throw std::runtime_error("OPIF assembly bound");
        Assembly a;a.size=total;a.crc=crc;a.count=count;a.fragments.resize(count);a.seen.resize(count);reserved+=total;it=partial.emplace(key,std::move(a)).first;
      }
      auto& a=it->second;
      if(a.size!=total||a.crc!=crc||a.count!=count)throw std::runtime_error("OPIF inconsistent fragments");
      if(a.seen[index]){
        if(a.fragments[index].size()!=bytes||!std::equal(a.fragments[index].begin(),a.fragments[index].end(),p+40))throw std::runtime_error("OPIF conflicting duplicate fragment");
      }else{
        if(a.bytes+bytes>total)throw std::runtime_error("OPIF payload overflow");
        a.fragments[index].assign(p+40,p+length);a.seen[index]=true;++a.received;a.bytes+=bytes;
      }
      if(a.received==a.count){
        if(a.bytes!=a.size)throw std::runtime_error("OPIF logical length mismatch");
        Complete message{key,crc,{}};message.body.reserve(total);
        for(const auto& fragment:a.fragments)message.body.insert(message.body.end(),fragment.begin(),fragment.end());
        if(opif_crc32c(message.body.data(),message.body.size())!=crc)throw std::runtime_error("OPIF logical CRC32C mismatch");
        if(complete.size()>=64||complete_bytes+total>4194304)throw std::runtime_error("OPIF completed queue bound");
        complete_bytes+=total;complete.push_back(std::move(message));reserved-=total;partial.erase(it);
      }
      offset+=length+4;
    }
    if(offset)raw.erase(raw.begin(),raw.begin()+offset);
  }
};
}
extern "C" void* opif_decoder_create(){try{return new Decoder();}catch(...){return nullptr;}}
extern "C" void opif_decoder_destroy(void* handle){delete static_cast<Decoder*>(handle);}
extern "C" int opif_decoder_feed(void* handle,const uint8_t* data,size_t size){
  auto* d=static_cast<Decoder*>(handle);if(!d)return -1;
  try{if(!d->error.empty())return -1;d->feed(data,size);return 0;}catch(const std::exception& e){d->error=e.what();return -1;}
}
extern "C" const char* opif_decoder_error(void* handle){auto* d=static_cast<Decoder*>(handle);return d?d->error.c_str():"OPIF decoder missing";}
extern "C" int opif_decoder_next(void* handle,uint64_t* metadata,uint8_t* body,size_t capacity){
  auto* d=static_cast<Decoder*>(handle);if(!d||!d->error.empty())return -1;if(d->complete.empty())return 0;
  auto& m=d->complete.front();if(capacity<m.body.size())return -1;
  metadata[0]=std::get<0>(m.key);metadata[1]=std::get<1>(m.key);metadata[2]=std::get<2>(m.key);metadata[3]=m.body.size();metadata[4]=m.crc;
  if(!m.body.empty())std::memcpy(body,m.body.data(),m.body.size());d->complete_bytes-=m.body.size();d->complete.pop_front();return 1;
}
