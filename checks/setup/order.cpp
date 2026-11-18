#include <cstdio>
#include <cstring>
#include <exception>
#include "tut_v1/Order.h"
int main(int argc, char** argv) {
    char bytes[256] = {};
    tut::v1::Order order;
    order.wrapAndApplyHeader(bytes, 0, sizeof bytes);
    try {
        if (argc > 1 && std::strcmp(argv[1], "wrong") == 0) order.putNote("hi", 2);
        else {
            order.fillsCount(0);
            order.putTrader("pat", 3);
            if (argc < 2 || std::strcmp(argv[1], "incomplete") != 0) order.putNote("hi", 2);
#ifdef SBE_ENABLE_PRECEDENCE_CHECKS
            order.checkEncodingIsComplete();
#endif
        }
        std::puts("ACCEPTED");
        return 0;
    } catch (const std::exception& e) {
        std::printf("REJECTED: %s\n", e.what());
        return 1;
    }
}
