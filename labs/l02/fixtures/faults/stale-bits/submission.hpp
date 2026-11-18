// [claim: WP1-BUFFERS] [claim: WP1-OWNERSHIP] [claim: WP1-ALLOCATION]
#pragma once
#include "api.hpp"
#include <cstring>
#include "tut_v1/Order.h"
#include "audit.hpp"
inline std::size_t encode(const Input& in, char* b, std::size_t capacity) {
    tut::v1::Order o;
    o.wrapAndApplyHeader(b, 0, capacity);
    o.orderId(in.id);
    o.price().mantissa(in.price);
    o.quantity(in.qty);
    o.stopPrice(in.has_stop ? in.stop : tut::v1::Order::stopPriceNullValue());
    char symbol[8]{};
    std::memcpy(symbol, in.symbol.data(), in.symbol.size());
    o.putSymbol(symbol);
    o.side(in.side == 'B' ? tut::v1::Side::BUY : tut::v1::Side::SELL);
    o.flags().ioc(in.ioc).postOnly(in.post_only).hidden(in.hidden);
    o.clientTag(in.tag);
    std::memset(b + 8 + 38, 0, 2);
    auto& f = o.fillsCount(in.count);
    for (unsigned i=0; i<in.count; ++i) {
        f.next().fillPrice(in.fills[i].price).fillQty(in.fills[i].qty).venue(in.fills[i].venue);
    }
    o.putTrader(in.trader.data(), static_cast<std::uint16_t>(in.trader.size()));
    o.putNote(in.note.data(), static_cast<std::uint16_t>(in.note.size()));
    return 8 + o.encodedLength();
}
inline Audit capture(char* b, std::size_t received) {
    tut::v1::MessageHeader h(b, received);
    tut::v1::Order o;
    o.wrapForDecode(b, 8, h.blockLength(), h.version(), received);
    auto& f = o.fills(); while (f.hasNext()) f.next();
    Audit a;
    a.length = o.traderLength();
    o.getTrader(a.storage.data(), a.storage.size());
    a.owns = true;
    return a;
}
inline std::uint64_t consume(char* b, std::size_t received) {
    tut::v1::MessageHeader h(b, received);
    tut::v1::Order o;
    o.wrapForDecode(b, 8, h.blockLength(), h.version(), received);
    auto& f = o.fills(); while (f.hasNext()) f.next();
    auto trader = o.getTraderAsStringView();
    auto note = o.getNoteAsStringView();
    return o.quantity() + trader.size() + note.size();
}
