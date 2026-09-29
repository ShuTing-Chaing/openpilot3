// Standalone Android NPU E2E using OPIF export and installed OPIF libraries.
// All four outputs are compared; this tool is never linked into the App.
// Timings here include allocated outputs/profiling. Use opif-server --benchmark
// for production-runtime A/B/A timings with its preallocated recurrent buffers.
#include "onnxruntime_c_api.h"
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <dlfcn.h>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

const OrtApi* api;
OrtAllocator* allocator;
void check(OrtStatus* status) {
  if (status) { std::string error=api->GetErrorMessage(status); api->ReleaseStatus(status); throw std::runtime_error(error); }
}
const char* ins[]={"new_img","desire","traffic_convention","action_t","state_img_q","state_desire_q","state_feat_q"};
const char* outs[]={"outputs","next_state_img_q","next_state_desire_q","next_state_feat_q"};
const std::vector<int64_t> shapes[]={{2,6,128,256},{8},{1,2},{1,2},{2,5,6,128,256},{132,1,8},{128,1,16384}};
const std::vector<int64_t> output_shapes[]={{1,18452},{2,5,6,128,256},{132,1,8},{128,1,16384}};
const size_t sizes[]={393216,32,8,8,1966080,4224,8388608};
const size_t output_sizes[]={73808,1966080,4224,8388608};
using Clock=std::chrono::steady_clock;

struct Session {
  OrtSession* handle=nullptr;
  std::array<OrtValue*,7> inputs{};
  OrtValue* main_output=nullptr;
  std::string path;
  Session(OrtEnv* env,const OrtEpDevice* device,const std::string& model,const std::string& profile):path(model) {
    OrtSessionOptions* options=nullptr;check(api->CreateSessionOptions(&options));
    try {
      check(api->AddSessionConfigEntry(options,"session.disable_cpu_ep_fallback","1"));
      check(api->SetSessionExecutionMode(options,ORT_SEQUENTIAL));
      check(api->AddSessionConfigEntry(options,"session.intra_op.allow_spinning","0"));
      check(api->AddSessionConfigEntry(options,"session.inter_op.allow_spinning","0"));
      check(api->SetIntraOpNumThreads(options,1));check(api->SetInterOpNumThreads(options,1));
      check(api->SetSessionGraphOptimizationLevel(options,ORT_ENABLE_EXTENDED));
      check(api->EnableProfiling(options,profile.c_str()));
      const char* keys[]={"backend_type","offload_graph_io_quantization","enable_htp_fp16_precision","htp_arch","soc_model","device_id","htp_performance_mode","htp_graph_finalization_optimization_mode","profiling_level","profiling_file_path"};
      std::string csv=profile+".csv";
      const char* values[]={"htp","0","1","81","87","0","sustained_high_performance","3","basic",csv.c_str()};
      check(api->SessionOptionsAppendExecutionProvider_V2(options,env,&device,1,keys,values,10));
      std::cerr<<"create_session_start "<<model<<std::endl;
      check(api->CreateSession(env,model.c_str(),options,&handle));
      std::cerr<<"create_session_ready "<<model<<std::endl;
      api->ReleaseSessionOptions(options); options=nullptr;
      size_t count=0;check(api->SessionGetInputCount(handle,&count));if(count!=7)throw std::runtime_error("input count");
      check(api->SessionGetOutputCount(handle,&count));if(count!=4)throw std::runtime_error("output count");
      for(size_t i=0;i<7;++i) {
        char* name=nullptr;check(api->SessionGetInputName(handle,i,allocator,&name));
        bool same=std::strcmp(name,ins[i])==0;allocator->Free(allocator,name);if(!same)throw std::runtime_error("input name/order");
        auto type=(i==0||i==4)?ONNX_TENSOR_ELEMENT_DATA_TYPE_UINT8:ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT;
        check(api->CreateTensorAsOrtValue(allocator,shapes[i].data(),shapes[i].size(),type,&inputs[i]));
        void* data=nullptr;check(api->GetTensorMutableData(inputs[i],&data));std::memset(data,0,sizes[i]);
      }
      for(size_t i=0;i<4;++i) {
        char* name=nullptr;check(api->SessionGetOutputName(handle,i,allocator,&name));
        bool same=std::strcmp(name,outs[i])==0;allocator->Free(allocator,name);if(!same)throw std::runtime_error("output name/order");
      }
    } catch(...) {if(options)api->ReleaseSessionOptions(options);close();throw;}
  }
  ~Session(){close();}
  void close() {
    if(main_output){api->ReleaseValue(main_output);main_output=nullptr;}
    for(auto& v:inputs)if(v){api->ReleaseValue(v);v=nullptr;}
    if(handle) {
      char* filename=nullptr;OrtStatus* status=api->SessionEndProfiling(handle,allocator,&filename);
      if(status)api->ReleaseStatus(status);if(filename)allocator->Free(allocator,filename);
      api->ReleaseSession(handle);handle=nullptr;
    }
  }
  double run(const std::vector<uint8_t>& bytes,const std::array<float,12>& scalars) {
    size_t offset=0;
    for(size_t i=0;i<4;++i) {
      void* data=nullptr;check(api->GetTensorMutableData(inputs[i],&data));
      if(i==0)std::memcpy(data,bytes.data(),sizes[i]);
      else {std::memcpy(data,reinterpret_cast<const uint8_t*>(scalars.data())+offset,sizes[i]);offset+=sizes[i];}
    }
    if(main_output){api->ReleaseValue(main_output);main_output=nullptr;}
    const OrtValue* feed[7];for(size_t i=0;i<7;++i)feed[i]=inputs[i];
    OrtValue* output[4]={};auto start=Clock::now();
    OrtStatus* error=api->Run(handle,nullptr,ins,feed,7,outs,4,output);
    double ms=std::chrono::duration<double,std::milli>(Clock::now()-start).count();
    if(error){for(auto v:output)if(v)api->ReleaseValue(v);check(error);}
    for(size_t i=0;i<4;++i) {
      OrtTensorTypeAndShapeInfo* info=nullptr;check(api->GetTensorTypeAndShape(output[i],&info));
      size_t rank=0;check(api->GetDimensionsCount(info,&rank));std::vector<int64_t> dims(rank);check(api->GetDimensions(info,dims.data(),rank));
      ONNXTensorElementDataType dtype;check(api->GetTensorElementType(info,&dtype));api->ReleaseTensorTypeAndShapeInfo(info);
      if(dims!=output_shapes[i]||dtype!=(i==1?ONNX_TENSOR_ELEMENT_DATA_TYPE_UINT8:ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT))throw std::runtime_error("output tensor ABI");
      void* data=nullptr;check(api->GetTensorMutableData(output[i],&data));
      if(i!=1)for(size_t j=0;j<output_sizes[i]/4;++j)if(!std::isfinite(static_cast<float*>(data)[j]))throw std::runtime_error("nonfinite output/state");
    }
    main_output=output[0];for(size_t i=0;i<3;++i){api->ReleaseValue(inputs[i+4]);inputs[i+4]=output[i+1];}
    return ms;
  }
  OrtValue* output(size_t i){return i==0?main_output:inputs[i+3];}
};

void generate(size_t frame,std::vector<uint8_t>& image,std::array<float,12>& scalar) {
  uint32_t random=0x6e624eb7U^static_cast<uint32_t>(frame*2654435761U);
  for(size_t i=0;i<image.size();++i) {
    random^=random<<13;random^=random>>17;random^=random<<5;
    image[i]=frame%97==0?0:frame%97==1?255:frame%97==2?static_cast<uint8_t>(i):static_cast<uint8_t>(random);
  }
  scalar.fill(0);if(frame%32==0)scalar[(frame/32)%8]=1;
  scalar[8]=1;scalar[10]=0.05f;scalar[11]=0;
}

int main(int argc,char** argv) {
  try {
    if(argc!=7)throw std::runtime_error("LIBDIR MODEL_A MODEL_B_OR_SINGLE OUTDIR FRAMES WARMUP");
    std::string libs=argv[1],modelA=argv[2],modelB=argv[3],outdir=argv[4];
    int frames=std::stoi(argv[5]),warmup=std::stoi(argv[6]);
    if(frames<1||frames>500||warmup<0||warmup>100)throw std::runtime_error("bounded frames/warmup required");
    if(!std::filesystem::create_directory(outdir))throw std::runtime_error("output directory already exists");
    void* lib=dlopen((libs+"/libonnxruntime.so").c_str(),RTLD_NOW|RTLD_LOCAL);if(!lib)throw std::runtime_error(dlerror());
    auto entry=reinterpret_cast<const OrtApiBase*(*)()>(dlsym(lib,"OrtGetApiBase"));if(!entry)throw std::runtime_error("ORT entry missing");
    if(std::strcmp(entry()->GetVersionString(),"1.27.0"))throw std::runtime_error("ORT version mismatch");
    api=entry()->GetApi(27);if(!api)throw std::runtime_error("ORT API27 missing");check(api->GetAllocatorWithDefaultOptions(&allocator));
    OrtEnv* env=nullptr;check(api->CreateEnv(ORT_LOGGING_LEVEL_WARNING,"OpifMaskDeviceE2E",&env));
    check(api->RegisterExecutionProviderLibrary(env,"QNNExecutionProvider",(libs+"/libonnxruntime_providers_qnn.so").c_str()));
    const OrtEpDevice*const* devices=nullptr;size_t count=0;check(api->GetEpDevices(env,&devices,&count));const OrtEpDevice* npu=nullptr;
    for(size_t i=0;i<count;++i)if(std::strcmp(api->EpDevice_EpName(devices[i]),"QNNExecutionProvider")==0&&api->HardwareDevice_Type(api->EpDevice_Device(devices[i]))==OrtHardwareDeviceType_NPU)npu=devices[i];
    if(!npu)throw std::runtime_error("QNN NPU unavailable");
    std::ofstream log(outdir+"/frames.jsonl");size_t different=0;
    {
      Session a(env,npu,modelA,outdir+"/a");
      std::unique_ptr<Session> b;if(modelB!="single")b=std::make_unique<Session>(env,npu,modelB,outdir+"/b");
      std::vector<uint8_t> image(393216);std::array<float,12> scalars;
      for(int frame=0;frame<frames+warmup;++frame) {
        generate(frame,image,scalars);double ta=a.run(image,scalars),tb=0;bool equal=true;
        log<<"{\"frame\":"<<frame<<",\"warmup\":"<<(frame<warmup?"true":"false")<<",\"a_ms\":"<<ta;
        if(b) {
          tb=b->run(image,scalars);log<<",\"b_ms\":"<<tb<<",\"output_byte_differences\":[";
          for(size_t i=0;i<4;++i) {
            void* pa=nullptr;void* pb=nullptr;check(api->GetTensorMutableData(a.output(i),&pa));check(api->GetTensorMutableData(b->output(i),&pb));
            size_t errors=0;if(std::memcmp(pa,pb,output_sizes[i])) {
              auto x=static_cast<uint8_t*>(pa),y=static_cast<uint8_t*>(pb);
              for(size_t j=0;j<output_sizes[i];++j)errors+=x[j]!=y[j];
            }
            if(i)log<<',';log<<errors;equal=equal&&errors==0;
          }
          log<<"],\"all_outputs_bit_exact\":"<<(equal?"true":"false");if(!equal)++different;
        }
        log<<"}\n";log.flush();
      }
    }
    std::ofstream summary(outdir+"/result.json");summary<<"{\"completed\":true,\"measured_frames\":"<<frames<<",\"warmup\":"<<warmup<<",\"different_frames\":"<<different<<",\"pair\":"<<(modelB=="single"?"false":"true")<<",\"npu_only\":true,\"performance_mode\":\"sustained_high_performance\"}\n";
    check(api->UnregisterExecutionProviderLibrary(env,"QNNExecutionProvider"));api->ReleaseEnv(env);
    return different?2:0;
  }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
