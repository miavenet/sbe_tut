// [claim: WP4-PERFORMANCE]
#include "submission.hpp"
#include <chrono>
#include <algorithm>
#include <iostream>
#include <vector>
using namespace seam;
int main(){try{
 for(unsigned offered:{1u,4u})for(unsigned batch:{1u,2u}){
  Queue q;unsigned accepted=0,rejected=0,delivered[2]={0,0},max_backlog=0;std::uint64_t bytes=0,seq=1;
  std::vector<long long> samples;samples.reserve(200); // setup, excluded from codec scope
  for(unsigned tick=0;tick<50;++tick){
   for(unsigned i=0;i<offered;++i){auto p=encode_order(accepted+1,1,'B');Frame f;need(make_frame(f,p.bytes.data(),p.size,ORDER_TYPE,9),"adapter");stamp(f,seq,7);
    auto t=std::chrono::steady_clock::now();bool ok=offer(q,f);auto end=std::chrono::steady_clock::now();
    samples.push_back(std::chrono::duration_cast<std::chrono::nanoseconds>(end-t).count());
    if(ok){++accepted;bytes+=f.size;}else{++rejected;--seq;}
   }
   max_backlog=std::max(max_backlog,unsigned(q.write-std::min(q.read[0],q.read[1])));
   for(unsigned c=0;c<2;++c){Frame f;for(unsigned i=0;i<batch;++i)if(pop(q,c,f))++delivered[c];}
  }
  for(unsigned c=0;c<2;++c){Frame f;while(pop(q,c,f))++delivered[c];}
  need(accepted+rejected==50*offered&&delivered[0]==accepted&&delivered[1]==accepted&&bytes==accepted*86&&max_backlog<=2,"load accounting");
  std::sort(samples.begin(),samples.end());
  std::cout<<"{\"offered_per_tick\":"<<offered<<",\"drain_batch\":"<<batch<<",\"ticks\":50,\"accepted\":"<<accepted<<",\"rejected\":"<<rejected<<",\"bytes\":"<<bytes<<",\"backlog_max\":"<<max_backlog<<",\"p50_offer_ns\":"<<samples[(samples.size()-1)/2]<<",\"p99_offer_ns\":"<<samples[(samples.size()-1)*99/100]<<",\"samples_ns\":[";
  for(std::size_t i=0;i<samples.size();++i)std::cout<<(i?",":"")<<samples[i];std::cout<<"]}\n";
 }
 return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
