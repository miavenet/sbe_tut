// [claim: WP1-BUFFERS] [claim: WP1-OWNERSHIP] [claim: WP1-ALLOCATION]
#pragma once
#include <array>
#include <cstddef>
struct Audit {
    std::array<char,256> storage{};
    const char* borrowed = nullptr;
    std::size_t length = 0;
    bool owns = false;
    const char* data() const { return owns ? storage.data() : borrowed; }
};
