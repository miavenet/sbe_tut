// [claim: WP3-VALIDATE] [claim: WP3-NESTED] [claim: WP3-ORDER]
#include "submission.hpp"
#include <fstream>
#include <iostream>
#include <iterator>
#include <functional>
using Bytes=std::vector<char>;
Bytes load(const std::string& p){std::ifstream f(p,std::ios::binary);require(bool(f),"fixture missing");return Bytes(std::istreambuf_iterator<char>(f),{});}
void word(Bytes& b,size_t p,unsigned v){b.at(p)=char(v);b.at(p+1)=char(v>>8);}
void add16(Bytes& b,unsigned v){b.push_back(char(v));b.push_back(char(v>>8));}
void add32(Bytes& b,unsigned v){for(int i=0;i<4;++i)b.push_back(char(v>>(8*i)));}
void add64(Bytes& b,std::int64_t v){for(int i=0;i<8;++i)b.push_back(char(std::uint64_t(v)>>(8*i)));}
void data(Bytes& b,const std::string& s){add16(b,s.size());b.insert(b.end(),s.begin(),s.end());}
Bytes nested(unsigned variant){
    Bytes b;for(auto n:{4,2,92,0})add16(b,n);add32(b,44+variant);
    add16(b,2);add16(b,variant==1?0:2);
    if(variant!=1){
        add16(b,7);add16(b,12);add16(b,2);
        add64(b,100);add32(b,3);add64(b,-200);add32(b,5);data(b,"AB");
        add16(b,9);add16(b,12);add16(b,0);data(b,"");
    }
    data(b,variant==1?"empty":"end");return b;
}
int main(int argc,char** argv){
 try{
    require(argc==3,"arguments");std::string mode=argv[2];unsigned good=0,bad=0;
    auto reject=[&](Bytes b,size_t n,bool nest,const std::string& id){
        // Valid backing storage deliberately exceeds the bytes actually received.
        b.resize(std::max(size_t(262144),b.size()),0);unsigned state=17;bool caught=false;
        try{auto r=nest?read_nested(b.data(),n):read_order(b.data(),n);(void)r;state=99;}
        catch(const std::exception&){caught=true;}
        require(caught && state==17, ("accepted malformed "+id).c_str());++bad;
    };
    if(mode=="all" || mode=="order" || mode=="validate"){
        for(int v=0;v<2;++v){auto b=load(std::string(argv[1])+"/order-v"+std::to_string(v)+".bin");
            auto r=read_order(b.data(),b.size());require(r.prices==std::vector<std::int64_t>{12340,12345} && r.sizes==std::vector<std::uint32_t>{60,40} && r.trader=="pat" && r.note=="hi" && r.end==b.size(),"order values/cursor");++good;
            if(mode!="order"){
                for(size_t n=0;n<b.size();++n)reject(b,n,false,"order truncation "+std::to_string(n));
                for(auto pair:std::vector<std::pair<size_t,unsigned>>{{0,0},{0,33},{0,65535},{2,99},{4,99},{6,3},{size_t(8+34+4*v),0},{size_t(8+34+4*v),11},{size_t(8+34+4*v),65535},{size_t(10+34+4*v),65535},{size_t(10+34+4*v),65534},{size_t(70+6*v),65535},{size_t(70+6*v),65534},{size_t(75+6*v),65535}}){auto x=b;word(x,pair.first,pair.second);reject(x,x.size(),false,"header/count/data");}
                auto extra=b;extra.push_back(0);reject(extra,extra.size(),false,"trailing byte");
            }
        }
        // Accepted declared compatible v2 contains only unknown fixed tails.
        auto b=load(std::string(argv[1])+"/order-v1.bin");Bytes future(b.begin(),b.begin()+46);
        word(future,0,42);word(future,6,2);future.insert(future.end(),{'R','O','O','T'});add16(future,15);add16(future,2);
        for(int j=0;j<2;++j){future.insert(future.end(),b.begin()+50+13*j,b.begin()+63+13*j);future.insert(future.end(),{'X','Y'});}
        future.insert(future.end(),b.begin()+76,b.end());auto r=read_order(future.data(),future.size());require(r.trader=="pat" && r.note=="hi" && r.end==future.size() && r.prices.size()==2,"compatible v2 cursor");++good;
        // Empty structures, maximum legal lengths/counts and a wide overflow probe.
        if(mode!="order"){
            Bytes empty(b.begin(),b.begin()+46);add16(empty,13);add16(empty,0);data(empty,"");data(empty,"");
            auto e=read_order(empty.data(),empty.size());require(e.end==empty.size() && e.prices.empty() && e.trader.empty(),"empty structure");++good;
            Bytes maxdata(b.begin(),b.begin()+46);add16(maxdata,13);add16(maxdata,0);data(maxdata,std::string(65534,'a'));data(maxdata,"");
            require(read_order(maxdata.data(),maxdata.size()).trader.size()==65534,"maximum data");++good;
            auto nulldata=maxdata;nulldata.insert(nulldata.end()-2,'a');word(nulldata,50,65535);reject(nulldata,nulldata.size(),false,"null data length");
            // Count max is valid metadata but cannot fit under this adapter's frame cap.
            auto count=b;word(count,48,65534);reject(count,count.size(),false,"count exceeds received");
            char small[8]={};Cursor c{small,8};bool caught=false;try{c.entries(std::numeric_limits<size_t>::max(),13);}catch(const std::exception&){caught=true;}require(caught,"wide count multiplication");++good;
            auto shortv1=b;shortv1.erase(shortv1.begin()+42,shortv1.begin()+46);word(shortv1,0,34);reject(shortv1,shortv1.size(),false,"v1 minimum root");
            auto shortg=b;shortg.erase(shortg.begin()+75);shortg.erase(shortg.begin()+62);word(shortg,46,12);reject(shortg,shortg.size(),false,"v1 minimum entry");
        }
    }
    if(mode=="all" || mode=="validate" || mode=="nested"){
        // A zero count must not bypass the metadata maximum. Enough bytes do not legalize null.
        for(int k=0;k<5;++k){
            bool nest=k>=2;unsigned root=(k==1||k==4)?65535:(nest?4:38);
            Bytes x(8+root+(k==3?14:4)+(nest?2:4),0);
            word(x,0,root);word(x,2,nest?2:1);word(x,4,nest?92:91);word(x,6,nest?0:1);
            auto p=8+root;word(x,p,(k==0||k==2)?65535:(nest?2:13));
            if(k==3){word(x,p+2,1);word(x,p+6,65535);x.resize(p+14);}
            reject(x,x.size(),nest,"null dimension "+std::to_string(k));
            // Adjacent legal metadata must remain accepted, including empty groups.
            if(k==1||k==4){x.erase(x.begin()+8);word(x,0,65534);}
            else word(x,k==3?p+6:p,65534);
            if(nest)validate_nested(x.data(),x.size());else validate_order(x.data(),x.size());++good;
        }
    }
    if(mode=="all" || mode=="nested"){
        for(unsigned k=0;k<2;++k){auto b=nested(k);if(k==0)require(b==load(std::string(argv[1])+"/nested.bin"),"nested oracle bytes");auto r=read_nested(b.data(),b.size());
            require(r.end==b.size(),"nested end");
            if(k==0)require(r.channels==std::vector<std::uint16_t>{7,9} && r.prices==std::vector<std::int64_t>{100,-200} && r.sizes==std::vector<std::uint32_t>{3,5} && r.labels==std::vector<std::string>{"AB",""} && r.note=="end","nested values");
            else require(r.channels.empty() && r.prices.empty() && r.note=="empty","empty outer has no child dimensions");++good;
            for(size_t n=0;n<b.size();++n)reject(b,n,true,"nested truncation "+std::to_string(n));
        }
        auto b=nested(0);
        for(auto x:std::vector<std::pair<size_t,unsigned>>{{0,0},{2,1},{4,91},{6,1},{12,0},{14,65535},{18,0},{20,65535},{46,65535},{52,0},{54,65534},{56,65535},{58,65535}}){auto m=b;word(m,x.first,x.second);reject(m,m.size(),true,"nested corrupt field "+std::to_string(x.first));}
        Bytes tape;for(auto k:{0,1}){auto f=nested(k);add32(tape,f.size());tape.insert(tape.end(),f.begin(),f.end());}
        auto results=read_tape(tape);require(results.size()==2 && results[1].note=="empty","tape boundary");++good;
        for(size_t n=1;n<tape.size();++n){if(n==4+nested(0).size())continue;Bytes t(tape.begin(),tape.begin()+n);bool caught=false;unsigned state=17;try{auto r=read_tape(t);(void)r;state=99;}catch(const std::exception&){caught=true;}require(caught && state==17,"tape truncation atomicity");++bad;}
        for(unsigned n:{0u,7u,262145u,0xffffffffu}){auto t=tape;for(int i=0;i<4;++i)t[i]=char(n>>(8*i));bool caught=false;try{read_tape(t);}catch(const std::exception&){caught=true;}require(caught,"frame length overflow");++bad;}
    }
    std::cout<<"PASS mode="<<mode<<" valid="<<good<<" rejected="<<bad<<"\n";return 0;
 }catch(const std::exception& e){std::cout<<"FAIL "<<e.what()<<"\n";return 1;}
}
