// [claim: WP2-MATRIX] [claim: WP2-ARCHIVE]
#pragma once
#include <cstdint>
#include <vector>
#include <string>
#include <array>
#include <stdexcept>
#include <cstring>
struct Fill { std::int64_t price; std::uint32_t qty; std::uint8_t venue=255; };
struct Record {
    std::uint64_t id=0;
    std::int64_t price=0;
    std::uint32_t qty=0;
    std::int32_t stop=INT32_MIN;
    std::array<char,8> symbol{};
    char side='B';
    bool ioc=false, post=false, hidden=false;
    std::uint32_t client=UINT32_MAX;
    std::vector<Fill> fills;
    std::string trader,note;
    std::size_t cursor=0;
};
struct Archive { std::vector<Record> records; std::vector<char> raw; };
// Supplied framing: little-endian uint32 length includes the SBE header.
inline std::uint32_t read32(const char* p) {
    std::uint32_t n=0;
    for(unsigned i=0;i<4;++i)n|=std::uint32_t(static_cast<unsigned char>(p[i]))<<(8*i);
    return n;
}
inline void append_frame(std::vector<char>& tape,const std::vector<char>& frame) {
    auto n=frame.size();
    if(n>1024)throw std::runtime_error("course frame bound");
    for(unsigned i=0;i<4;++i)tape.push_back(char(n>>(8*i)));
    tape.insert(tape.end(),frame.begin(),frame.end());
}
