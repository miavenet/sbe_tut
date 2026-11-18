// [claim: WP4-FRAME] [claim: WP4-REPLAY] [claim: WP4-RELEASE]
#pragma once
#include <array>
#include <cstdint>
#include <cstddef>
#include <cstring>
#include <stdexcept>
#include <limits>
#include "hash32.hpp"
namespace seam {
constexpr std::size_t HEADER=32,MAX_PAYLOAD=1408,MAX_FRAME=HEADER+MAX_PAYLOAD;
// Hypothetical fixture IDs; allocate real IDs through your own system's registry.
constexpr std::uint16_t ORDER_TYPE=60000,CONTROL_TYPE=60001;
struct Frame {std::array<char,MAX_FRAME> bytes{};std::size_t size=0;};
inline void need(bool b,const char* why){if(!b)throw std::runtime_error(why);}
inline std::uint64_t le(const char* p,unsigned n) noexcept {std::uint64_t v=0;for(unsigned i=0;i<n;++i)v|=std::uint64_t((unsigned char)p[i])<<(8*i);return v;}
inline void put(char* p,std::uint64_t v,unsigned n) noexcept {for(unsigned i=0;i<n;++i)p[i]=char(v>>(8*i));}
inline std::uint32_t checksum(const Frame& f) noexcept {
    Hash32 x;x.update(f.bytes.data(),16);x.update(f.bytes.data()+20,12);
    x.update(f.bytes.data()+32,f.size-32);return x.digest();
}
struct Cursor {
    const char* b;std::size_t n,p=0;
    void take(std::size_t k){need(p<=n&&k<=n-p,"received length");p+=k;}
    std::uint16_t word(){auto q=p;take(2);return le(b+q,2);}
    void entries(std::size_t count,std::size_t width){need(width&&count<=(n-p)/width,"count/remaining");take(count*width);}
    void data(std::size_t max){auto n=word();need(n<=max,"null data length");take(n);}
};
struct Event {bool control=false;std::uint64_t id=0,tick=0;std::int64_t price=0;std::uint32_t qty=0,rule=1;char side=0;};
struct Output {std::uint64_t id=0,tick=0;std::int64_t total=0;};
struct Seen {std::uint32_t origin=0;std::uint64_t id=0;Frame frame;};
// Bounded teaching state; 32 unique requests, 32 outputs, no hidden eviction policy.
struct State {
    std::uint64_t next=1,tick=0;std::uint32_t epoch=7,rule=1;
    std::int64_t total=0;bool halted=false;std::size_t used=0,out_count=0;
    std::array<Seen,32> seen{};std::array<Output,32> outputs{};Frame last;
};
enum class Verdict {applied,duplicate,rejected,halted};
inline bool same(const Frame& a,const Frame& b) noexcept {return a.size==b.size&&std::memcmp(a.bytes.data(),b.bytes.data(),a.size)==0;}
// Capacity is reclaimed only after BOTH consumers pass a slot. Single-threaded model.
struct Ingress {std::array<Frame,2> slots{};std::uint64_t read=0,write=0;};
inline bool enqueue(Ingress& q,const Frame& f) noexcept {if(q.write-q.read==2)return false;q.slots[q.write++%2]=f;return true;}
inline bool take_draft(Ingress& q,Frame& f) noexcept {if(q.read==q.write)return false;f=q.slots[q.read++%2];return true;}
struct Queue {std::array<Frame,2> slots{};std::uint64_t write=0;std::array<std::uint64_t,2> read{};};
inline bool pop(Queue& q,unsigned consumer,Frame& out) noexcept {
    if(q.read[consumer]==q.write)return false;
    out=q.slots[q.read[consumer]%2];++q.read[consumer];return true;
}
struct Release {bool apply=false,ack=false;};
enum class Policy {non_gated,pair,quorum};
struct Boundary {bool stamped=false,local_persisted=false,secondary_persisted=false,other_persisted=false;std::uint32_t leader_epoch=7,current_epoch=7;};
// Submission implements these decisions. Supplied codec/helper code is below this interface.
void validate_order(const char*,std::size_t);
bool make_frame(Frame&,const char*,std::size_t,std::uint16_t,std::uint32_t) noexcept;
void stamp(Frame&,std::uint64_t&,std::uint32_t) noexcept;
bool offer(Queue&,const Frame&) noexcept;
Verdict receive(State&,const Frame&) noexcept;
Release release(Policy,const Boundary&) noexcept;
bool price_e4(std::int64_t,std::int64_t&) noexcept;
}
