// Decodes a Java-encoded v1 Order (out/order-v1.bin) with the generated C++ flyweights,
// then re-encodes the same values in C++ and writes out/order-v1-cpp.bin.
#include <cstdio>
#include <fstream>
#include <iostream>
#include <iterator>
#include <vector>
#include "tut_v1/MessageHeader.h"
#include "tut_v1/Order.h"

using namespace tut::v1;

int main(int argc, char **argv)
{
    std::ifstream in(argv[1], std::ios::binary);
    std::vector<char> buf((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());

    MessageHeader hdr(buf.data(), 0, buf.size(), 0);
    std::cout << "header: blockLength=" << hdr.blockLength() << " templateId=" << hdr.templateId()
              << " schemaId=" << hdr.schemaId() << " version=" << hdr.version() << "\n";

    Order order;
    order.wrapForDecode(buf.data(), MessageHeader::encodedLength(), hdr.blockLength(), hdr.version(), buf.size());
    std::cout << std::hex << "orderId=0x" << order.orderId() << " clientTag=0x" << order.clientTag() << std::dec
              << " price=" << order.price().mantissa() << "e" << (int)order.price().exponent()
              << " qty=" << order.quantity() << " symbol='" << order.getSymbolAsString() << "'"
              << " side=" << (char)order.side() << " ioc=" << order.flags().ioc() << "\n";
    auto &fills = order.fills();
    while (fills.hasNext())
    {
        fills.next();
        std::cout << "fill: px=" << fills.fillPrice() << " qty=" << fills.fillQty() << " venue=" << (int)fills.venue() << "\n";
    }
    std::cout << "trader='" << order.getTraderAsString() << "' note='" << order.getNoteAsString() << "'"
              << " encodedLength=" << order.encodedLength() << "\n";

    char out[256] = {};
    Order enc;
    enc.wrapAndApplyHeader(out, 0, sizeof(out))
        .orderId(0x1122334455667788ULL)
        .quantity(100)
        .stopPrice(Order::stopPriceNullValue())
        .putSymbol("AAPL\0\0\0\0")
        .side(Side::BUY)
        .clientTag(0xCAFEBABE);
    enc.price().mantissa(12345);
    enc.flags().clear().ioc(true).hidden(true);
    auto &ef = enc.fillsCount(2);
    ef.next().fillPrice(12340).fillQty(60).venue(7);
    ef.next().fillPrice(12345).fillQty(40).venue(9);
    enc.putTrader(std::string("pat"));
    enc.putNote(std::string("hi"));
    const std::size_t len = MessageHeader::encodedLength() + enc.encodedLength();
    std::ofstream(argv[2], std::ios::binary).write(out, (std::streamsize)len);
    std::cout << "C++ encoded " << len << " bytes -> " << argv[2] << "\n";
    return 0;
}
