// [claim: WP2-MUTATIONS]
#include "submission.hpp"
#include <fstream>
#include <iostream>
#include <iterator>
static std::vector<char> load(const std::string& p){std::ifstream f(p,std::ios::binary);return {std::istreambuf_iterator<char>(f),{}};}
int main(int argc,char**argv){
    if(argc!=2)return 2;
    auto b=load(std::string(argv[1])+"/case-0-v1.bin");
    tut::v0::Order wrong;
    wrong.wrapForDecode(b.data(),8,34,0,b.size());
    auto count=wrong.fills().count();
    std::cout<<"COMPILED_ROOT count="<<count<<" expected=2\n";
    if(count!=51966)return 1;
    // All buffers contain valid underlying storage; generated bounds checks stay on.
    for(const char* name:{"group-add","group-data","data-insert"}) {
        auto x=load(std::string(argv[1])+"/"+name+".bin");
        bool mismatch=false;
        try{auto r=decode_v0(x.data(),x.size());mismatch=r.trader!="pat" || r.note!="hi" || r.cursor!=x.size() || r.fills.size()!=2 || r.fills[1].price!=12345;}
        catch(const std::exception&){mismatch=true;}
        std::cout<<"UNSAFE "<<name<<" detected="<<mismatch<<"\n";
        if(!mismatch)return 1;
    }
    return 0;
}
