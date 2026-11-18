// [claim: WP3-VALIDATE] [claim: WP3-NESTED]
#pragma once
#include <cstdint>
#include <cstddef>
#include <vector>
#include <string>
#include <stdexcept>
#include <limits>
struct ViewResult {
    std::vector<std::int64_t> prices;
    std::vector<std::uint32_t> sizes;
    std::vector<std::uint16_t> channels;
    std::vector<std::string> labels;
    std::string trader,note;
    std::size_t end=0;
};
inline void require(bool b,const char* s){if(!b)throw std::runtime_error(s);}
inline std::uint16_t u16(const char* b,std::size_t p){return (unsigned char)b[p]|((unsigned char)b[p+1]<<8);}
// Caller supplies actual received length. Every advance uses subtraction before addition.
struct Cursor {
    const char* b; std::size_t n,p=0;
    void take(std::size_t len){require(p<=n && len<=n-p,"truncated structure");p+=len;}
    std::uint16_t word(){auto at=p;take(2);return u16(b,at);}
    void data(std::uint16_t maximum){auto len=word();require(len<=maximum,"data null/limit");take(len);}
    void entries(std::size_t count,std::size_t width){
        require(width!=0 && p<=n && count<=(n-p)/width,"count/remaining");take(count*width);
    }
};
// Local policy: Order schema91/template1 versions0,1,2; v2 only fixed optional tails.
// Nested capture schema92/template2 version0; independent uint32 LE tape frame lengths.
inline std::uint32_t u32(const char* b){std::uint32_t v=0;for(int i=0;i<4;++i)v|=std::uint32_t((unsigned char)b[i])<<(8*i);return v;}
