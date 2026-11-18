// [claim: WP3-ORDER] [claim: WP3-VALIDATE] [claim: WP3-NESTED]
#pragma once
#include "api.hpp"
#include "tut_v1/Order.h"
#include "diag_nested/Capture.h"
inline void validate_order(const char* b,std::size_t received) {
    require(received<=262144,"frame bound");
    Cursor c{b,received}; c.take(8);
    auto root=u16(b,0),version=u16(b,6);
    require(root<65535,"null root length");
    require(u16(b,2)==1 && u16(b,4)==91 && version<=2,"unsupported contract");
    require(root>=(version?38:34),"short root");c.take(root);
    auto width=c.word(),count=c.word();
    require(width>=(version?13:12) && width<=tut::v1::GroupSizeEncoding::blockLengthMaxValue(),"short entry");
    require(count<=tut::v1::GroupSizeEncoding::numInGroupMaxValue(),"count null/limit");
    c.entries(count,width);
    c.data(tut::v1::VarStringEncoding::lengthMaxValue());
    c.data(tut::v1::VarStringEncoding::lengthMaxValue());
    require(c.p==received,"extra bytes outside contract");
}
inline ViewResult read_order(char* b,std::size_t received) {
    validate_order(b,received);
    tut::v1::Order o; o.wrapForDecode(b,8,u16(b,0),u16(b,6),received);
    ViewResult out; auto& g=o.fills();
    
    out.trader=o.getTraderAsString();out.note=o.getNoteAsString();
    out.end=8+o.encodedLength();return out;
}
inline void validate_nested(const char* b,std::size_t received) {
    require(received<=262144,"frame bound");Cursor c{b,received};c.take(8);
    require(u16(b,2)==2 && u16(b,4)==92 && u16(b,6)==0,"unsupported capture");
    auto root=u16(b,0);require(root<65535,"null capture root length");require(root>=4,"short capture root");c.take(root);
    auto outer=c.word(),count=c.word();
    require(outer>=2 && outer<=diag::nested::GroupSizeEncoding::blockLengthMaxValue() && count<=diag::nested::GroupSizeEncoding::numInGroupMaxValue(),"outer dimensions");
    require(count<=(received-c.p)/outer,"outer count/remaining");
    for(unsigned i=0;i<count;++i){
        c.take(outer);auto inner=c.word(),ticks=c.word();
        require(inner>=12 && inner<=diag::nested::GroupSizeEncoding::blockLengthMaxValue() && ticks<=diag::nested::GroupSizeEncoding::numInGroupMaxValue(),"inner dimensions");
        c.entries(ticks,inner);c.data(diag::nested::VarStringEncoding::lengthMaxValue());
    }
    c.data(diag::nested::VarStringEncoding::lengthMaxValue());require(c.p==received,"capture tail");
}
inline ViewResult read_nested(char* b,std::size_t received) {
    validate_nested(b,received);
    diag::nested::Capture o;o.wrapForDecode(b,8,u16(b,0),u16(b,6),received);
    ViewResult out;auto& batches=o.batches();
    while(batches.hasNext()){
        batches.next();out.channels.push_back(batches.channel());auto& ticks=batches.ticks();
        while(ticks.hasNext()){ticks.next();out.prices.push_back(ticks.price());out.sizes.push_back(ticks.size());}
        out.labels.push_back(batches.getLabelAsString());
    }
    out.note=o.getNoteAsString();out.end=8+o.encodedLength();return out;
}
inline std::vector<ViewResult> read_tape(std::vector<char>& tape) {
    std::vector<ViewResult> staged;
    for(std::size_t p=0;p<tape.size();){
        require(tape.size()-p>=4,"prefix truncated");auto n=u32(tape.data()+p);p+=4;
        require(n>=8 && n<=262144 && n<=tape.size()-p,"frame length");
        staged.push_back(read_nested(tape.data()+p,n));p+=n;
    }
    return staged;
}
