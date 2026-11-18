// [claim: WP4-CHECKSUM]
#include "hash32.hpp"
#include <array>
#include <iostream>
int main(){std::array<unsigned char,1408> data{};for(unsigned i=0;i<data.size();++i)data[i]=(i*17+3)%256;
 for(unsigned n:{0u,1u,3u,15u,16u,17u,31u,32u,1408u}){
  seam::Hash32 x;for(unsigned i=0;i<n;++i)x.update(data.data()+i,1);
  auto h=seam::Hash32::oneshot(data.data(),n);if(h!=x.digest())return 1;
  std::cout<<n<<" "<<h<<"\n";
 }return 0;}
