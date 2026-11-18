// [claim: WP1-WIRE]
#include "submission.hpp"
#include "cases.hpp"
#include <cstdio>
#include <cstring>
#include <exception>
int main(int argc,char** argv) {
    try {
        char b[2048];
        for(unsigned i=0;i<cases.size();++i) {
            std::memset(b,0xaa,sizeof b);
            auto n=encode(cases[i],b,sizeof b);
            if(n>sizeof b) return 1;
            std::printf("WIRE %u ",i);
            for(std::size_t j=0;j<n;++j) std::printf("%02x",static_cast<unsigned char>(b[j]));
            std::puts("");
            tut::v0::MessageHeader h(b,n);tut::v0::Order d;
            if(n>=42 && h.blockLength()==34 && h.templateId()==1 && h.schemaId()==91 && h.version()==0){
                d.wrapForDecode(b,8,h.blockLength(),h.version(),n);
                auto qty=d.quantity(); auto id=d.orderId();
                std::printf("ACCESS %u %u %llu\n",i,qty,static_cast<unsigned long long>(id));
            }
        }
        for(int i=1;i<argc;++i) {
            auto* f=std::fopen(argv[i],"rb");if(!f)return 2;
            auto n=std::fread(b,1,sizeof b,f);std::fclose(f);
            auto m=decode_market(b,n);
            std::printf("MARKET %d %d %d %u ",i-1,m.mantissa,m.exponent,m.size);
            for(char c:m.ticker)std::printf("%02x",static_cast<unsigned char>(c));
            std::puts("");
        }
        return 0;
    } catch(const std::exception& e) { std::printf("EXCEPTION %s\n",e.what());return 1; }
}
