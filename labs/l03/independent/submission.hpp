// [claim: WP2-MATRIX] [claim: WP2-ARCHIVE]
#pragma once
#include "api.hpp"
#include "tut_v0/Order.h"
#include "tut_v1/Order.h"
// Input records in this lab are bounded by the supplied fixture corpus.
template<class O> std::vector<char> write_record(const Record& in) {
    std::vector<char> b(1024,0); O o;
    o.wrapAndApplyHeader(b.data(),0,b.size());
    o.orderId(in.id); o.price().mantissa(in.price); o.quantity(in.qty);
    o.stopPrice(in.stop); o.putSymbol(in.symbol.data());
    o.side(static_cast<decltype(o.side())>(in.side));
    o.flags().clear().ioc(in.ioc).postOnly(in.post).hidden(in.hidden);
    if constexpr(O::sbeSchemaVersion()==1)o.clientTag(in.client);
    auto& g=o.fillsCount(static_cast<std::uint16_t>(in.fills.size()));
    for(const auto& f:in.fills){g.next().fillPrice(f.price).fillQty(f.qty);
        if constexpr(O::sbeSchemaVersion()==1)g.venue(f.venue);}
    o.putTrader(in.trader.data(),static_cast<std::uint16_t>(in.trader.size()));
    o.putNote(in.note.data(),static_cast<std::uint16_t>(in.note.size()));
    b.resize(8+o.encodedLength()); return b;
}
inline std::vector<char> encode_v0(const Record& in){return write_record<tut::v0::Order>(in);}
inline std::vector<char> encode_v1(const Record& in){return write_record<tut::v1::Order>(in);}
template<class O> Record read_record(char* b,std::size_t received) {
    tut::v0::MessageHeader h(b,0,received,0);
    if(h.schemaId()!=91 || h.templateId()!=1 || h.version()>2)
        throw std::runtime_error("unsupported contract");
    O o;
    o.wrapForDecode(b,8,h.blockLength(),h.version(),received);
    Record out;
    out.id=o.orderId(); out.price=o.price().mantissa(); out.qty=o.quantity();
    out.stop=o.stopPrice(); o.getSymbol(out.symbol.data(),8); out.side=char(o.side());
    out.ioc=o.flags().ioc(); out.post=o.flags().postOnly(); out.hidden=o.flags().hidden();
    if constexpr(O::sbeSchemaVersion()==1)out.client=o.clientTag();
    auto& g=o.fills();
    while(g.hasNext()) {
        g.next(); Fill f{g.fillPrice(),g.fillQty(),255};
        if constexpr(O::sbeSchemaVersion()==1)f.venue=g.venue();
        out.fills.push_back(f);
    }
    out.trader=o.getTraderAsString(); out.note=o.getNoteAsString();
    out.cursor=8+o.encodedLength(); return out;
}
inline Record decode_v0(char* b,std::size_t n){return read_record<tut::v0::Order>(b,n);}
inline Record decode_v1(char* b,std::size_t n){return read_record<tut::v1::Order>(b,n);}
// TODO(L03-T1): the archive must keep each original frame, unknown extensions included.
inline Archive archive_tape(const std::vector<char>& tape) {
    Archive out;
    for(std::size_t p=0;p<tape.size();) {
        if(tape.size()-p<4)throw std::runtime_error("truncated prefix");
        auto n=read32(tape.data()+p); p+=4;
        if(n<8 || n>1024 || n>tape.size()-p)throw std::runtime_error("bad frame length");
        std::vector<char> frame(tape.begin()+p,tape.begin()+p+n);
        out.records.push_back(decode_v1(frame.data(),frame.size()));
        auto old=decode_v0(frame.data(),frame.size());
        append_frame(out.raw,encode_v0(old));
        p+=n;
    }
    return out;
}
