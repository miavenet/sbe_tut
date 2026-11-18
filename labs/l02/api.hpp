// [claim: WP1-BUFFERS] [claim: WP1-OWNERSHIP] [claim: WP1-ALLOCATION]
#pragma once
#include <array>
#include <cstdint>
#include <cstddef>
#include <string_view>
struct Fill { std::int64_t price; std::uint32_t qty; std::uint8_t venue; };
struct Input {
    std::uint64_t id; std::int64_t price; std::uint32_t qty;
    bool has_stop; std::int32_t stop; std::string_view symbol;
    char side; bool ioc, post_only, hidden;
    std::uint32_t tag;
    std::array<Fill,2> fills; unsigned count;
    std::string_view trader, note;
};
struct Market { std::int32_t mantissa; int exponent; std::uint16_t size; std::array<char,4> ticker; };
