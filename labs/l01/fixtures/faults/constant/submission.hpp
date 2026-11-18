// [claim: WP1-WIRE] [claim: WP1-MARKET]
#pragma once
#include "api.hpp"
#include <cstring>
#include "tut_v0/Order.h"
#include "market/Quote.h"
inline std::size_t encode(const Input& in, char* b, std::size_t capacity) {
    tut::v0::Order o;
    o.wrapAndApplyHeader(b, 0, capacity);
    o.orderId(in.id);
    o.price().mantissa(in.price);
    o.quantity(in.qty);
    o.stopPrice(in.has_stop ? in.stop : tut::v0::Order::stopPriceNullValue());
    char symbol[8]{};
    std::memcpy(symbol, in.symbol.data(), in.symbol.size());
    o.putSymbol(symbol);
    o.side(in.side == 'B' ? tut::v0::Side::BUY : tut::v0::Side::SELL);
    o.flags().clear().ioc(in.ioc).postOnly(in.post_only).hidden(in.hidden);
    auto& f = o.fillsCount(in.count);
    for (unsigned i=0; i<in.count; ++i) {
        f.next().fillPrice(in.fills[i].price).fillQty(in.fills[i].qty);
    }
    o.putTrader(in.trader.data(), static_cast<std::uint16_t>(in.trader.size()));
    o.putNote(in.note.data(), static_cast<std::uint16_t>(in.note.size()));
    auto n=8+o.encodedLength(); std::memmove(b+25,b+24,n-24);b[24]=-2;return n+1;
}
inline Market decode_market(char* b, std::size_t received) {
    market::MessageHeader h(b, received);
    market::Quote q;
    q.wrapForDecode(b, 8, h.blockLength(), h.version(), received);
    Market m{q.price().mantissa(), q.price().exponent(), q.size(), {}};
    q.getTicker(m.ticker.data(), 4);
    return m;
}
