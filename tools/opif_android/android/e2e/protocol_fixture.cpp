// Synthetic accelerator fixture, production protocol server/socket/pipeline.
#include "opif_protocol.h"
#include <chrono>
#include <cmath>
#include <csignal>
#include <iostream>
#include <thread>
std::atomic<bool> stopped{false};
void stop(int) { stopped.store(true); }
struct Runtime : opif::InferenceRuntime {
  void begin_session() override {}
  void end_session() noexcept override {}
  opif::InferenceResponse infer(const opif::InferenceRequest& request) override {
    std::this_thread::sleep_for(std::chrono::milliseconds(60));
    opif::InferenceResponse r; r.inference_time_us=60000;
    r.output.resize(opif::kOutputElements);
    for(size_t i=0;i<r.output.size();++i) r.output[i]=float(i)*.125f+float(request.request_id);
    if(request.desire==7) r.output[3000]=NAN; // only the omitted hidden section
    return r;
  }
};
int main(){signal(SIGTERM,stop);signal(SIGINT,stop);Runtime runtime;opif::UdpServer server(runtime,0,opif::Transport::Tcp);std::cout<<server.port()<<std::endl;server.run(stopped);}
