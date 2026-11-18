// [claim: WP4-FRAME] [claim: WP4-CODEC] [claim: WP4-REPLAY] [claim: WP4-RELEASE] [claim: WP4-ALLOC]
#include "submission.hpp"
#include "fixtures/release-traces.hpp"
#include <fstream>
#include <vector>
#include <iostream>
#include <string>
#include <chrono>
#include <algorithm>
using namespace seam;
static unsigned checks=0;
void ck(bool ok,const char* id){++checks;if(!ok)throw std::runtime_error(id);}
std::vector<char> read(const std::string& p){std::ifstream f(p,std::ios::binary);need(bool(f),"file input");return {std::istreambuf_iterator<char>(f),{}};}
void save(const std::string& p,const Frame& f){std::ofstream o(p,std::ios::binary|std::ios::app);o.write(f.bytes.data(),f.size);need(bool(o),"tape write");}
Frame framed(Frame p,std::uint64_t seq=1,std::uint16_t type=ORDER_TYPE,std::uint32_t origin=9){Frame f;ck(make_frame(f,p.bytes.data(),p.size,type,origin),"valid adapter input");stamp(f,seq,7);return f;}
Frame fixture(const std::string& path){auto b=read(path);Frame p;ck(b.size()<=p.bytes.size(),"fixture size");std::copy(b.begin(),b.end(),p.bytes.begin());p.size=b.size();return p;}
void rehash(Frame& f){put(f.bytes.data()+16,checksum(f),4);}
bool business_same(const State& a,const State& b){
    if(a.total!=b.total||a.tick!=b.tick||a.rule!=b.rule||a.used!=b.used||a.out_count!=b.out_count||a.next!=b.next||!same(a.last,b.last))return false;
    for(std::size_t i=0;i<a.out_count;++i)if(a.outputs[i].id!=b.outputs[i].id||a.outputs[i].tick!=b.outputs[i].tick||a.outputs[i].total!=b.outputs[i].total)return false;
    for(std::size_t i=0;i<a.used;++i)if(a.seen[i].id!=b.seen[i].id||a.seen[i].origin!=b.seen[i].origin||!same(a.seen[i].frame,b.seen[i].frame))return false;
    return true;
}
void frame_checks(const std::string& dir){
    auto p=fixture(dir+"/order-v1.bin"),f=framed(p),gold=fixture(dir+"/envelope.bin");
    if(!same(f,gold)){
        std::size_t at=0,limit=std::min(f.size,gold.size);
        while(at<limit && f.bytes[at]==gold.bytes[at])++at;
        auto field = at < 8 ? "sequence" : at < 12 ? "origin" : at < 16 ? "stream" : at < 20 ? "checksum" : at < 24 ? "epoch" : at < 26 ? "msg_type" : at < 28 ? "length" : at < 32 ? "reserved" : "payload";
        throw std::runtime_error("independent envelope/checksum bytes: byte "+std::to_string(at)+" "+field+
            ": observed "+(at<f.size?std::to_string(static_cast<unsigned char>(f.bytes[at])):"missing")+
            ", expected "+(at<gold.size?std::to_string(static_cast<unsigned char>(gold.bytes[at])):"missing"));
    }
    std::cout<<"envelope bytes="<<f.size<<" payload="<<le(f.bytes.data()+26,2)<<" checksum="<<le(f.bytes.data()+16,4)<<"\n";
    Frame unchanged=f;
    for(std::size_t n=0;n<p.size;++n){Frame out=f;ck(!make_frame(out,p.bytes.data(),n,ORDER_TYPE,9),"every truncated payload rejects");ck(same(out,unchanged),"adapter failure leaves output unchanged");}
    for(auto off:{2,4,6}){auto bad=p;put(bad.bytes.data()+off,999,2);Frame out=f;ck(!make_frame(out,bad.bytes.data(),bad.size,ORDER_TYPE,9),"header dispatch rejects");}
    auto old=fixture(dir+"/order-v0.bin");ck(framed(old).size==111,"old archive input accepted");
    // A future version in the declared fixed-tail family is supported.
    auto future=fixture(dir+"/order-v2-tail.bin");auto forwarded=framed(future);ck(forwarded.size==121&&std::memcmp(forwarded.bytes.data()+32,future.bytes.data(),future.size)==0,"supported newer optional tails preserved raw");
    for(std::size_t off:{std::size_t(46),std::size_t(48),std::size_t(76),std::size_t(81)}){
        auto bad=p;put(bad.bytes.data()+off,65535,2);Frame out=f;ck(!make_frame(out,bad.bytes.data(),bad.size,ORDER_TYPE,9),"dimensions/data null or overflow rejects");}
    auto bad=p;bad.bytes[40]='?';Frame out=f;ck(!make_frame(out,bad.bytes.data(),bad.size,ORDER_TYPE,9),"unknown enum adapter reject");
    ck(!make_frame(out,p.bytes.data()+8,p.size-8,ORDER_TYPE,9),"missing SBE header rejects");
    ck(!make_frame(out,p.bytes.data(),p.size,1,9),"legacy msg_type cannot dispatch toy Order");
    ck(!make_frame(out,p.bytes.data(),1409,ORDER_TYPE,9),"oversize before memcpy");
    auto empty=encode_order(8,1,'B');put(empty.bytes.data()+46,tut::v1::GroupSizeEncoding::blockLengthNullValue(),2);ck(!make_frame(out,empty.bytes.data(),empty.size,ORDER_TYPE,9),"empty group null block length rejects");
    auto max_note=MAX_PAYLOAD-encode_order(8,1,'B').size;
    auto count_max=std::size_t(tut::v1::GroupSizeEncoding::numInGroupMaxValue());
    auto data_max=std::size_t(tut::v1::VarStringEncoding::lengthMaxValue());
    auto max=encode_order(8,1,'B',0,max_note);ck(max.size==1408&&framed(max).size==1440,"payload maximum accepts");
    unsigned rejected=0;for(auto n:{count_max,count_max+1,count_max+2,std::size_t(-1)})try{encode_order(1,1,'B',n);}catch(const std::exception&){++rejected;}
    ck(rejected==4,"wide count before narrowing and frame cap");rejected=0;
    for(auto n:{max_note+1,data_max,data_max+1,data_max+2,std::size_t(-1)})try{encode_order(1,1,'B',0,n);}catch(const std::exception&){++rejected;}
    ck(rejected==5,"wide length before narrowing and frame cap");
    std::int64_t scaled=0;ck(price_e4(12345,scaled)&&scaled==1234500LL,"price -2 to E4");
    ck(price_e4(INT64_MAX/100,scaled),"conversion upper accept");ck(!price_e4(INT64_MAX/100+1,scaled),"conversion overflow reject");
    ck(price_e4(INT64_MIN/100,scaled)&&!price_e4(INT64_MIN/100-1,scaled),"conversion lower boundary");
    tut::v1::Order o;Frame temp;o.wrapAndApplyHeader(temp.bytes.data(),0,MAX_PAYLOAD);
    auto early=o.encodedLength();auto complete=encode_order(1,1,'B');ck(early==38&&complete.size==54,"early length excludes trailing structure/header");
    Frame short_frame=framed(complete);put(short_frame.bytes.data()+26,early,2);rehash(short_frame);State s;ck(receive(s,short_frame)==Verdict::rejected,"early cursor framing rejected");
    std::cout<<"metadata count_max="<<tut::v1::GroupSizeEncoding::numInGroupMaxValue()<<" data_max="<<tut::v1::VarStringEncoding::lengthMaxValue()<<" early_body="<<early<<" complete_payload="<<complete.size<<"\n";
}
std::uint32_t business_digest(const State& s){
    Hash32 x;char b[8];auto add=[&](std::uint64_t v,unsigned n){put(b,v,n);x.update(b,n);};
    add(s.next,8);add(s.tick,8);add(s.rule,4);add(std::uint64_t(s.total),8);add(s.used,4);add(s.out_count,4);
    for(unsigned i=0;i<s.out_count;++i){add(s.outputs[i].id,8);add(s.outputs[i].tick,8);add(std::uint64_t(s.outputs[i].total),8);}
    return x.digest();
}
void replay_checks(const std::string& dir){
    std::array<Frame,5> input={framed(encode_control(1,10),1,CONTROL_TYPE),framed(encode_order(11,3,'B'),2),framed(encode_order(11,3,'B'),3),framed(encode_control(2,20),4,CONTROL_TYPE),framed(encode_order(12,4,'S'),5)};
    // Bounded draft ingress precedes the one-writer stamper. No draft is assigned
    // an identity until removed. A failed offer retains the original draft.
    std::array<Frame,5> drafts=input;
    for(auto& f:drafts){put(f.bytes.data(),0,8);put(f.bytes.data()+16,0,4);put(f.bytes.data()+20,0,4);}
    Ingress ingress;ck(enqueue(ingress,drafts[0])&&enqueue(ingress,drafts[1]),"bounded draft ingress");
    ck(!enqueue(ingress,drafts[2])&&ingress.write==2,"ingress reject retains draft");
    std::uint64_t next=1;Frame draft;
    for(unsigned i=0;i<5;++i){
        ck(take_draft(ingress,draft)&&same(draft,drafts[i]),"ingress exact order/bytes");
        stamp(draft,next,7);ck(same(draft,input[i]),"single-writer stamp after dequeue");input[i]=draft;
        if(i+2<5)ck(enqueue(ingress,drafts[i+2]),"retry exact draft after capacity freed");
    }
    Queue q;State a,b;ck(offer(q,input[0])&&offer(q,input[1]),"queue initial offer");Frame popped;
    ck(pop(q,0,popped)&&same(popped,input[0]),"fast consumer reads first");ck(receive(a,popped)==Verdict::applied,"first control applies");
    auto before=q;ck(!offer(q,input[2]),"slow consumer backpressure");ck(q.write==before.write&&same(q.slots[0],before.slots[0])&&same(q.slots[1],before.slots[1]),"reject cannot overwrite queued bytes");
    ck(pop(q,1,popped)&&same(popped,input[0]),"slow consumer barrier");ck(receive(b,popped)==Verdict::applied,"replica control");
    ck(offer(q,input[2]),"retry retains exact request");
    std::string tape="accepted.tape";{std::ofstream clear(tape,std::ios::binary);}
    save(tape,input[0]);save(tape,input[1]);save(tape,input[2]);
    for(unsigned c=0;c<2;++c)while(pop(q,c,popped)){auto v=receive(c?b:a,popped);ck(v==Verdict::applied||v==Verdict::duplicate,"queued apply");}
    for(unsigned i=3;i<input.size();++i){ck(offer(q,input[i]),"post-drain offer");save(tape,input[i]);for(unsigned c=0;c<2;++c){ck(pop(q,c,popped)&&same(popped,input[i]),"accepted IDs bytes order");ck(receive(c?b:a,popped)==Verdict::applied,"accepted apply");}}
    ck(business_same(a,b),"two replicas exact state/output");ck(a.total==-5&&a.out_count==2&&a.outputs[0].id==11&&a.outputs[0].tick==10&&a.outputs[0].total==3&&a.outputs[1].id==12&&a.outputs[1].tick==20&&a.outputs[1].total==-5,"independent output oracle");
    State fresh;auto bytes=read(tape);std::size_t pos=0,records=0;
    while(pos<bytes.size()){
        ck(bytes.size()-pos>=32,"tape header");auto n=le(bytes.data()+pos+26,2);ck(n<=1408&&n<=bytes.size()-pos-32,"tape independent boundary");
        Frame f;f.size=32+n;std::copy_n(bytes.data()+pos,f.size,f.bytes.data());ck(same(f,input[records]),"persisted bytes identity");auto v=receive(fresh,f);ck(v==Verdict::applied||v==Verdict::duplicate,"fresh replay accepts");pos+=f.size;++records;
    }
    ck(records==5&&business_same(fresh,a),"fresh replay exact state/output");
    std::uint32_t expected;std::ifstream digest_file(dir+"/business-digest.txt");digest_file>>expected;
    ck(bool(digest_file)&&business_digest(a)==expected&&business_digest(b)==expected&&business_digest(fresh)==expected,"independent business-state digest");
    std::cout<<"business_digest="<<expected<<" replicas=equal replay=equal\n";
    auto before_dup=fresh;ck(receive(fresh,input[4])==Verdict::duplicate&&business_same(fresh,before_dup),"protocol duplicate distinct from request duplicate");
    // Deterministic counterexample: same valid bytes, hidden environment differs.
    auto only_order=framed(encode_order(77,3,'B'));State x,y;y.rule=2;y.tick=99;
    ck(receive(x,only_order)==Verdict::applied&&receive(y,only_order)==Verdict::applied,"both code versions decode");ck(x.total!=y.total&&x.outputs[0].tick!=y.outputs[0].tick,"unlogged rule/time divergence");
    State logged1,logged2;logged2.rule=2;logged2.tick=99;
    ck(receive(logged1,input[0])==Verdict::applied&&receive(logged2,input[0])==Verdict::applied,"logged activation resets both");
    ck(receive(logged1,input[1])==Verdict::applied&&receive(logged2,input[1])==Verdict::applied&&business_same(logged1,logged2),"logged activation/time closes divergence");
    std::cout<<"accepted sequences=1,2,3,4,5 request_ids=11,11,12 outputs=11:10:3,12:20:-5 replay_equal=1 hidden_rule_totals="<<x.total<<","<<y.total<<"\n";
    // Independent archive transfer: concatenated v0/v1, incomplete second frame must not apply it.
    auto v0=framed(fixture(dir+"/order-v0.bin"));auto v1=framed(fixture(dir+"/order-v1.bin"),2,ORDER_TYPE,10);
    State archive;ck(receive(archive,v0)==Verdict::applied,"archived old order");auto snap=archive;v1.size--;
    ck(receive(archive,v1)==Verdict::rejected&&business_same(archive,snap),"torn archived second frame no partial mutation");
}
void adverse_checks(){
    auto valid=framed(encode_order(1,7,'B'));unsigned bad_count=0;
    auto reject=[&](Frame bad){State s,before;ck(receive(s,bad)==Verdict::rejected,"adverse rejects");ck(business_same(s,before)&&s.halted,"poison no business mutation");ck(receive(s,valid)==Verdict::halted,"halt latch");++bad_count;};
    for(std::size_t n=0;n<valid.size;++n){auto f=valid;f.size=n;if(n>=32)rehash(f);reject(f);}
    auto bad=valid;bad.bytes[16]^=1;reject(bad);
    bad=valid;put(bad.bytes.data(),2,8);rehash(bad);reject(bad);
    bad=valid;put(bad.bytes.data()+20,8,4);rehash(bad);reject(bad);
    bad=valid;put(bad.bytes.data()+28,1,4);rehash(bad);reject(bad);
    bad=valid;put(bad.bytes.data()+12,2,4);rehash(bad);reject(bad);
    bad=valid;put(bad.bytes.data()+26,1409,2);reject(bad);
    bad=valid;put(bad.bytes.data()+24,123,2);rehash(bad);reject(bad);
    bad=valid;bad.bytes[32+40]='?';rehash(bad);reject(bad);
    bad=valid;put(bad.bytes.data()+32+24,0,4);rehash(bad);reject(bad);
    // Structural error at the final field occurs after a valid request and quantity.
    bad=valid;put(bad.bytes.data()+bad.size-2,65535,2);rehash(bad);reject(bad);
    State s;ck(receive(s,valid)==Verdict::applied,"collision baseline");auto snapshot=s;
    bad=framed(encode_order(1,8,'B'),2);ck(receive(s,bad)==Verdict::rejected&&business_same(s,snapshot),"same request different bytes rejects");
    State bounded;for(unsigned i=1;i<=32;++i)ck(receive(bounded,framed(encode_order(i,1,'B'),i))==Verdict::applied,"bounded request store accepts");snapshot=bounded;
    ck(receive(bounded,framed(encode_order(33,1,'B'),33))==Verdict::rejected&&business_same(snapshot,bounded),"bounded store full rejects atomically");
    std::cout<<"adverse cases="<<bad_count<<" each latched/no business mutation\n";
}
void release_checks(){
    unsigned cases=0;for(unsigned bits=0;bits<16;++bits)for(unsigned stale=0;stale<2;++stale)for(auto p:{Policy::non_gated,Policy::pair,Policy::quorum}){
        Boundary b{bool(bits&1),bool(bits&2),bool(bits&4),bool(bits&8),stale?6u:7u,7};
        bool want=b.stamped&&!stale&&(p==Policy::non_gated||(b.local_persisted&&(p==Policy::pair?b.secondary_persisted:(b.secondary_persisted||b.other_persisted))));
        auto got=release(p,b);ck(got.apply==want&&got.ack==want,"release decision set");++cases;
    }
    std::array<std::array<bool,3>,3> applied{};
    for(const auto& step:release_trace){
        unsigned mask=0;unsigned policy=0;
        for(auto p:{Policy::non_gated,Policy::pair,Policy::quorum}){
            auto decision=release(p,step.boundary);ck(decision.apply==decision.ack,"trace ack requires successful apply assumption");
            if(decision.apply){mask|=1u<<policy;applied[policy][step.record-101]=true;} // identity-based effect: retry adds none
            ++policy;
        }
        ck(mask==step.eligible,step.event);
    }
    ck(applied[0]==std::array<bool,3>{true,true,false}&&applied[1]==std::array<bool,3>{false,true,false}&&applied[2]==std::array<bool,3>{false,true,false},"exact trace record release sets");
    std::cout<<"release_trace events=12 non_gated=101,102 pair=102 quorum=102 stale103=wait retry102=no-new-effect\n";
    std::cout<<"release decisions="<<cases<<" loss:non_gated=apply+ack pair=wait quorum=wait paused_secondary_with_other:quorum=apply+ack stale_leader=wait\n";
}
extern "C" void count_begin();extern "C" std::uint64_t count_end();void escape_string(const std::string&);
void allocation_checks(){
    auto loop=[](){std::uint64_t sum=0;for(unsigned i=0;i<1000;++i){auto p=encode_order(i+1,1,'B');Frame f;if(!make_frame(f,p.bytes.data(),p.size,ORDER_TYPE,9))return std::uint64_t(-1);std::uint64_t seq=i+1;stamp(f,seq,7);sum+=checksum(f);}return sum;};
    auto warm=loop();count_begin();auto result=loop();auto measured=count_end();ck(warm==result&&measured==0,"warmed bounded codec+frame+stamp new count");
    count_begin();std::string control(4096,'x');escape_string(control);auto hits=count_end();ck(hits>0,"owning-string allocation control hit");
    std::cout<<"alloc iterations=1000 new_calls="<<measured<<" long_string_control="<<hits<<" excludes=setup,IO,logging,errors,receive,replay malloc_not_instrumented=1\n";
}
int main(int argc,char** argv){try{
    need(argc>=2,"fixtures argument");std::string mode=argc>2?argv[2]:"all";
    if(mode=="all"||mode=="frame")frame_checks(argv[1]);
    if(mode=="all"||mode=="replay"){replay_checks(argv[1]);adverse_checks();}
    if(mode=="all"||mode=="release")release_checks();
    if(mode=="all"||mode=="allocation")allocation_checks();
    ck(checks>0,"valid mode");std::cout<<"PASS assertions="<<checks<<"\n";return 0;
}catch(const std::exception& e){std::cout<<"FAIL criterion="<<e.what()<<"\n";return 1;}}
