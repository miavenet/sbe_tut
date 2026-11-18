// Lesson 05 card L05-R4 workspace copy of the supplied codec adapter.
#pragma once
#include "api.hpp"
#include "tut_v1/Order.h"
#include "control/Control.h"
namespace seam {
// Adapter calls the learner's structural validator first; decode exceptions stay here.
inline Event decode(char* b,std::size_t n,std::uint16_t type) {
    Event e;
    if(type==ORDER_TYPE){
        validate_order(b,n);
        tut::v1::Order o;o.wrapForDecode(b,8,le(b,2),le(b+6,2),n);
        e.id=o.orderId();e.qty=o.quantity();e.price=o.price().mantissa();e.side=b[40]=='S'?'S':'B'; // TODO(L05-R4): unknown sides must be rejected, not turned into BUY
        need(e.id>0&&e.id<tut::v1::Order::orderIdNullValue(),"request ID");
        need(e.qty>0&&e.qty<=1000000,"quantity domain");
        need(e.side=='B'||e.side=='S',"unknown side rejected");
        need(e.price>0,"price domain");std::int64_t converted;need(price_e4(e.price,converted),"price conversion overflow");
        auto& g=o.fills();while(g.hasNext()){g.next();need(g.fillQty()>0&&g.fillQty()<=e.qty,"fill qty");need(g.fillPrice()>0,"fill price");}
        o.skipTrader();o.skipNote();need(8+o.encodedLength()==n,"cursor/frame boundary");
    }else if(type==CONTROL_TYPE){
        need(n==20&&le(b,2)==12&&le(b+2,2)==2&&le(b+4,2)==93&&le(b+6,2)==0,"control contract");
        control::Control c;c.wrapForDecode(b,8,12,0,n);e.control=true;e.rule=c.rule();e.tick=c.tick();
        need((e.rule==1||e.rule==2)&&e.tick<control::Control::tickNullValue(),"control domain");
    }else need(false,"msg_type dispatch");
    return e;
}
// Successful path uses no owning string convenience. Wide lengths validated BEFORE casts.
inline Frame encode_order(std::uint64_t id,std::uint32_t qty,char side,std::size_t count=0,std::size_t note_size=0) {
    using O=tut::v1::Order;
    need(side=='B'||side=='S',"input side");
    need(count<=tut::v1::GroupSizeEncoding::numInGroupMaxValue(),"wide count limit");
    need(note_size<=tut::v1::VarStringEncoding::lengthMaxValue(),"wide data limit");
    constexpr std::size_t base=8+O::sbeBlockLength()+4+2+2;
    need(count<=(MAX_PAYLOAD-base)/O::Fills::sbeBlockLength(),"encoded count bound");
    auto fixed=base+count*O::Fills::sbeBlockLength();need(note_size<=MAX_PAYLOAD-fixed,"encoded length bound");
    Frame payload;O o;o.wrapAndApplyHeader(payload.bytes.data(),0,MAX_PAYLOAD).orderId(id).quantity(qty)
      .stopPrice(O::stopPriceNullValue()).putSymbol("AAPL\0\0\0\0").side(side=='B'?tut::v1::Side::BUY:tut::v1::Side::SELL).clientTag(O::clientTagNullValue());
    o.price().mantissa(12345);o.flags().clear();auto& g=o.fillsCount(static_cast<std::uint16_t>(count));
    for(std::size_t i=0;i<count;++i)g.next().fillPrice(12345).fillQty(1).venue(O::Fills::venueNullValue());
    std::array<char,MAX_PAYLOAD> data{};o.putTrader(data.data(),0);o.putNote(data.data(),static_cast<std::uint16_t>(note_size));
    o.checkEncodingIsComplete();payload.size=8+o.encodedLength();need(payload.size==fixed+note_size,"precomputed size");return payload;
}
inline Frame encode_control(std::uint32_t rule,std::uint64_t tick){Frame p;control::Control c;c.wrapAndApplyHeader(p.bytes.data(),0,MAX_PAYLOAD).rule(rule).tick(tick);p.size=8+c.encodedLength();return p;}
// Already validated event: no exceptions, allocation, I/O, clock or config reads.
inline void apply(State& s,const Event& e) noexcept {
    if(e.control){s.rule=e.rule;s.tick=e.tick;return;}
    s.total+=(e.side=='B'?1:-1)*std::int64_t(e.qty)*s.rule;
    s.outputs[s.out_count++]={e.id,s.tick,s.total};
}
}
