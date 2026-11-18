// [claim: WP2-MATRIX] [claim: WP2-ARCHIVE]
#include "submission.hpp"
#include <fstream>
#include <iostream>
#include <iterator>
#include <algorithm>
static void need(bool p,const std::string& why){if(!p)throw std::runtime_error(why);}
static std::vector<char> load(const std::string& p){std::ifstream f(p,std::ios::binary);need(bool(f),"fixture missing");return {std::istreambuf_iterator<char>(f),{}};}
static Record input(unsigned k){
    Record r; r.id=0x1122334455667788ULL+k;r.price=12345-20000*int(k);r.qty=100+k;
    r.stop=k%2?0:INT32_MIN;
    std::memcpy(r.symbol.data(),k%2?"BONDXYZQ":"AAPL\0\0\0\0",8);
    r.side=k%2?'S':'B';r.ioc=k%2==0;r.post=k%2;r.hidden=k==0;
    r.client=k==3?UINT32_MAX:0xCAFEBABE + k;
    unsigned n=k==0?2:k-1;
    for(unsigned j=0;j<n;++j)r.fills.push_back({12340+5*int(j)+int(k),j==0?60u:40u,std::uint8_t(7+2*j)});
    r.trader=k==0?"pat":k==1?"":"auditor";r.note=k==0?"hi":k==2?"archive payload":"";
    return r;
}
static void equal(const Record& a,Record e,bool extensions,std::size_t cursor) {
    need(a.id==e.id,"orderId");need(a.price==e.price,"price");need(a.qty==e.qty,"quantity");
    need(a.stop==e.stop,"stopPrice");need(a.symbol==e.symbol,"symbol tail");need(a.side==e.side,"side");
    need(a.ioc==e.ioc && a.post==e.post && a.hidden==e.hidden,"all flags");
    need(a.client==(extensions?e.client:UINT32_MAX),"clientTag/null");
    need(a.fills.size()==e.fills.size(),"fill count");
    for(unsigned i=0;i<e.fills.size();++i){need(a.fills[i].price==e.fills[i].price,"fillPrice/stride");
        need(a.fills[i].qty==e.fills[i].qty,"fillQty/stride");
        need(a.fills[i].venue==(extensions?e.fills[i].venue:255),"venue/null");}
    need(a.trader==e.trader && a.note==e.note,"trailing data/cursor");need(a.cursor==cursor,"final cursor");
}
int main(int argc,char** argv){try{
    need(argc==3,"usage: runner fixture_dir mode");std::string dir=argv[1],mode=argv[2];
    if(mode=="matrix" || mode=="all") {
        for(unsigned k=0;k<4;++k)for(unsigned w=0;w<2;++w){
            auto r=input(k);auto b=w?encode_v1(r):encode_v0(r);
            auto expected=load(dir+"/case-"+std::to_string(k)+"-v"+std::to_string(w)+".bin");
            need(b==expected,"writer byte oracle case="+std::to_string(k)+" version="+std::to_string(w));
            for(unsigned reader=0;reader<2;++reader){try {
                auto out=reader?decode_v1(b.data(),b.size()):decode_v0(b.data(),b.size());
                equal(out,r,reader==1 && w==1,b.size());
                std::cout<<"MATRIX case="<<k<<" writer="<<w<<" reader="<<reader<<" all_fields=OK cursor="<<out.cursor<<" client="<<out.client<<"\n";
            } catch(const std::exception& e) { throw std::runtime_error("case="+std::to_string(k)+" writer="+std::to_string(w)+" reader="+std::to_string(reader)+": "+e.what()); }
            }
        }
    }
    if(mode=="archive" || mode=="all") {
        auto tape=load(dir+"/archive.bin");auto saved=tape;auto out=archive_tape(tape);
        need(out.records.size()==3,"archive record count");
        auto future=load(dir+"/future.bin");
        equal(out.records[0],input(2),false,load(dir+"/case-2-v0.bin").size());
        equal(out.records[1],input(0),true,85);equal(out.records[2],input(3),true,future.size());
        need(out.raw==saved,"raw unknown extension preservation including frame prefixes");
        std::fill(tape.begin(),tape.end(),char(0xAA));
        need(out.raw==saved && out.records[0].trader=="auditor","archive ownership after reuse");
        auto v1=load(dir+"/case-0-v1.bin");auto old=decode_v0(v1.data(),v1.size());auto lost=encode_v0(old);
        need(lost.size()==79 && lost!=v1,"unknown loss control");
        auto reread=decode_v1(lost.data(),lost.size());need(reread.client==UINT32_MAX,"loss control client null");
        for(auto f:reread.fills)need(f.venue==255,"loss control venue null");
        std::cout<<"ARCHIVE records=3 raw_equal=1 survives_reuse=1 old_reencode=85->79 client_null="<<reread.client<<"\n";
        for(auto bad: {std::vector<char>{1,0},std::vector<char>{100,0,0,0,1}}){
            bool rejected=false;try{archive_tape(bad);}catch(const std::exception&){rejected=true;}need(rejected,"truncated archive frame");}
    }
    std::cout<<"{\"status\":\"PASS\"}\n";return 0;
}catch(const std::exception& e){std::cout<<"FAIL "<<e.what()<<"\n";return 1;}}
