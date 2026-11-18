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
    // TODO(L01-I1): encode the optional stop price (present value, or the null value when absent)
    char symbol[8]{};
    std::memcpy(symbol, in.symbol.data(), in.symbol.size());
    o.putSymbol(symbol);
    o.side(in.side == 'B' ? tut::v0::Side::BUY : tut::v0::Side::SELL);
    // TODO(L01-I1): encode the flags bitset: clear all bits, then set ioc, postOnly, hidden from the input
    auto& f = o.fillsCount(in.count);
    for (unsigned i=0; i<in.count; ++i) {
        f.next().fillPrice(in.fills[i].price).fillQty(in.fills[i].qty);
    }
    o.putTrader(in.trader.data(), static_cast<std::uint16_t>(in.trader.size()));
    o.putNote(in.note.data(), static_cast<std::uint16_t>(in.note.size()));
    return o.encodedLength(); // TODO(L01-I1): return the full packet length, header included
}
inline Market decode_market(char* b, std::size_t received) {
    // TODO(L01-T1): decode the big-endian Quote with the generated market::MessageHeader and market::Quote.
    (void)b; (void)received; return {};
}
