// [claim: WP1-BUFFERS] [claim: WP1-OWNERSHIP] [claim: WP1-ALLOCATION]
#include "submission.hpp"
#include "cases.hpp"
#include <cstdio>
#include <cstring>
#include <exception>
extern "C" void count_begin();
extern "C" std::uint64_t count_end();
extern "C" std::size_t owning_control(const char*,std::size_t);
volatile std::uint64_t observed;
static void hex(const char* b,std::size_t n){for(std::size_t j=0;j<n;++j)std::printf("%02x",static_cast<unsigned char>(b[j]));std::puts("");}
int main(){
    try {
        char b[2048];
        for(unsigned i=0;i<cases.size();++i){
            std::memset(b,0xaa,sizeof b);
            auto n=encode(cases[i],b,sizeof b);if(n>sizeof b)return 1;
            std::printf("WIRE %u ",i);hex(b,n);
            auto original=capture(b,n);
            auto saved=original;
            char replacement_text[256];std::memset(replacement_text,'X',sizeof replacement_text);
            if(i==0)std::memcpy(replacement_text,"amy",3);
            Input replacement=cases[i];replacement.trader=std::string_view(replacement_text,cases[i].trader.size());
            encode(replacement,b,sizeof b);
            std::printf("AUDIT %u ",i);if(original.length>256)return 1;hex(original.data(),original.length);
            original.storage.fill('X');
            std::printf("COPIED %u ",i);if(saved.length>256)return 1;hex(saved.data(),saved.length);
            auto again=encode(cases[i],b,sizeof b);if(again>sizeof b)return 1;
            std::printf("REUSED %u ",i);hex(b,again);
        }
        for(int mode=0;mode<3;++mode){
            std::memset(b,mode==0?0xaa:0,sizeof b);
            tut::v1::Order o;o.wrapAndApplyHeader(b,0,sizeof b);
            if(mode==2)o.stopPrice(tut::v1::Order::stopPriceNullValue());
            std::printf("NULL %d %d\n",mode,o.stopPrice());
        }
        // Buffers, cases, and diagnostics are outside this warmed measured interval.
        for(int i=0;i<100;++i){auto n=encode(cases[i%4],b,sizeof b);observed=consume(b,n);}
        count_begin();
        std::uint64_t sum=0;
        for(int i=0;i<1000;++i){auto n=encode(cases[i%4],b,sizeof b);sum+=consume(b,n);}
        auto hits=count_end();observed=sum;
        std::printf("LOOP %llu %llu\n",static_cast<unsigned long long>(hits),static_cast<unsigned long long>(sum));
        count_begin();observed=owning_control(cases[3].trader.data(),cases[3].trader.size());auto control=count_end();
        std::printf("CONTROL %llu\n",static_cast<unsigned long long>(control));
        return 0;
    }catch(const std::exception& e){count_end();std::printf("EXCEPTION %s\n",e.what());return 1;}
}
