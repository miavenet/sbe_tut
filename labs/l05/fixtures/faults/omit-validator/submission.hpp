// [claim: WP4-FRAME] [claim: WP4-REPLAY] [claim: WP4-RELEASE] [claim: WP4-MIGRATION]
#pragma once
#include "api.hpp"
#include "codec.hpp"
namespace seam {
inline void validate_order(const char* b,std::size_t n){
    need(n<=MAX_PAYLOAD,"payload cap");Cursor c{b,n};c.take(8);
    auto root=le(b,2),v=le(b+6,2);
    need(le(b+2,2)==1&&le(b+4,2)==91&&v<=2,"schema/template/version policy");
    need(root>=(v?38:34),"root minimum");c.take(root);
    auto width=c.word(),count=c.word();need(width>=(v?13:12)&&width<=tut::v1::GroupSizeEncoding::blockLengthMaxValue(),"entry minimum/null");
    need(count<=tut::v1::GroupSizeEncoding::numInGroupMaxValue(),"count null");c.entries(count,width);
    c.data(tut::v1::VarStringEncoding::lengthMaxValue());c.data(tut::v1::VarStringEncoding::lengthMaxValue());
    need(c.p==n,"payload tail");
}
inline bool price_e4(std::int64_t p,std::int64_t& out) noexcept {
    constexpr std::int64_t factor=100;
    if(p>INT64_MAX/factor||p<INT64_MIN/factor)return false;
    out=p*factor;return true;
}
inline bool make_frame(Frame& out,const char* p,std::size_t n,std::uint16_t type,std::uint32_t origin) noexcept {
    try{
        need(n>=8&&n<=MAX_PAYLOAD,"payload length");Frame staged;
        std::memcpy(staged.bytes.data()+HEADER,p,n);staged.size=HEADER+n;
        (void)type; // full validation BEFORE publish
        put(staged.bytes.data()+12,1,4);put(staged.bytes.data()+8,origin,4);
        put(staged.bytes.data()+24,type,2);put(staged.bytes.data()+26,n,2);
        out=staged;return true;
    }catch(const std::exception&){return false;}
}
inline void stamp(Frame& f,std::uint64_t& next,std::uint32_t epoch) noexcept {
    put(f.bytes.data(),next++,8);put(f.bytes.data()+20,epoch,4);
    put(f.bytes.data()+16,checksum(f),4); // AFTER sequence and epoch
}
inline bool offer(Queue& q,const Frame& f) noexcept {
    auto slow=q.read[0]<q.read[1]?q.read[0]:q.read[1];
    if(q.write-slow>=q.slots.size())return false;
    q.slots[q.write%q.slots.size()]=f;++q.write;return true;
}
inline Verdict receive(State& s,const Frame& f) noexcept {
    if(s.halted)return Verdict::halted;
    try{
        need(f.size>=HEADER&&f.size<=MAX_FRAME,"frame length");auto b=f.bytes.data();auto n=le(b+26,2);
        need(n>=8&&n<=MAX_PAYLOAD&&n==f.size-HEADER,"received payload length");
        need(le(b+12,4)==1&&le(b+28,4)==0,"stream/reserved");
        need(le(b+16,4)==checksum(f),"checksum");need(le(b+20,4)==s.epoch,"epoch fence");
        auto seq=le(b,8);
        // Explicit course recovery policy: only exact last-frame retry is a protocol duplicate.
        if(seq+1==s.next&&same(f,s.last))return Verdict::duplicate;
        need(seq==s.next,"sequence gap/conflicting duplicate");
        Frame copy=f;Event e=decode(copy.bytes.data()+HEADER,n,le(b+24,2));
        State staged=s;
        if(!e.control){
            for(std::size_t i=0;i<s.used;++i)if(s.seen[i].origin==le(b+8,4)&&s.seen[i].id==e.id){
                const Frame& old=s.seen[i].frame;
                need(old.size==f.size&&std::memcmp(old.bytes.data()+HEADER,b+HEADER,n)==0,"request ID collision");
                staged.next++;staged.last=f;s=staged;return Verdict::duplicate;
            }
            need(s.used<s.seen.size()&&s.out_count<s.outputs.size(),"bounded state full");
            staged.seen[staged.used++]={std::uint32_t(le(b+8,4)),e.id,f};
        }
        apply(staged,e);staged.next++;staged.last=f;s=staged;return Verdict::applied;
    }catch(const std::exception&){s.halted=true;return Verdict::rejected;}
}
inline Release release(Policy p,const Boundary& b) noexcept {
    if(!b.stamped||b.leader_epoch!=b.current_epoch)return {};
    bool yes=p==Policy::non_gated||
      (b.local_persisted&&(p==Policy::pair?b.secondary_persisted:(b.secondary_persisted||b.other_persisted)));
    return {yes,yes}; // Model assumes apply finishes successfully before the ack is emitted.
}
}
