// [claim: WP3-ORDER]
#include "tut_v1/Order.h"
#include <fstream>
#include <iostream>
#include <vector>
#include <iterator>
#include <string>
int main(int argc,char** argv){
    if(argc!=3)return 2;
    std::ifstream in(argv[1],std::ios::binary);std::vector<char> b((std::istreambuf_iterator<char>(in)),{});
    if(b.size()!=85)return 2;b.resize(65536,0);
    using O=tut::v1::Order;
    std::string mode=argv[2];O o;
    try{
        o.wrapForDecode(b.data(),8,38,1,b.size());
        if(mode=="skip")std::cout<<"trader_length="<<o.getTraderAsString().size()<<"\n";
        else if(mode=="before-next"){auto& g=o.fills();std::cout<<"price="<<g.fillPrice()<<"\n";}
        else if(mode=="partial"){auto& g=o.fills();g.next();std::cout<<"trader_length="<<o.getTraderAsString().size()<<"\n";}
        else if(mode=="swap"){auto& g=o.fills();while(g.hasNext())g.next();auto n=o.getNoteAsString();auto t=o.getTraderAsString();std::cout<<"note="<<n<<" trader="<<t<<"\n";}
        else if(mode=="incomplete"){
            char out[256]={};o.wrapAndApplyHeader(out,0,sizeof(out));o.fillsCount(0);o.putTrader("pat",3);o.checkEncodingIsComplete();
        }else{
            std::cout<<"root_cursor="<<o.sbePosition()<<" remaining="<<85-o.sbePosition()<<" price_offset="<<O::priceEncodingOffset()<<"\n";
            auto& g=o.fills();std::cout<<"dimensions_cursor="<<o.sbePosition()<<" count="<<g.count()<<"\n";
            while(g.hasNext()){g.next();std::cout<<"entry_cursor="<<o.sbePosition()<<" px="<<g.fillPrice()<<" qty="<<g.fillQty()<<"\n";}
            auto t=o.getTraderAsString();std::cout<<"trader="<<t<<" cursor="<<o.sbePosition()<<"\n";
            auto n=o.getNoteAsString();std::cout<<"note="<<n<<" cursor="<<o.sbePosition()<<" body="<<o.encodedLength()<<"\n";
        }
        std::cout<<"ACCEPTED\n";return 0;
    }catch(const std::exception& e){std::cout<<"CAUGHT "<<e.what()<<"\n";return 1;}
}
