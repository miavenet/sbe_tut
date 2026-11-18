#pragma once
// Bounded xxHash32 adaptation for this course fixture.
// Upstream: Copyright (c) 2012-2021 Yann Collet. All rights reserved.
// Source: https://github.com/Cyan4973/xxHash
// License: BSD 2-Clause; full notice: ../../LICENSES/xxHash.txt.
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <exception>

namespace seam {
using u8 = std::uint8_t;
using u32 = std::uint32_t;

class Hash32 {
    static constexpr u32 A = 2654435761u;
    static constexpr u32 B = 2246822519u;
    static constexpr u32 C = 3266489917u;
    static constexpr u32 D = 668265263u;
    static constexpr u32 E = 374761393u;
    std::array<u8, 4096> bytes_{};
    std::size_t used_ = 0;
    u32 seed_ = 0;

    static u32 rotate(u32 value, unsigned n) noexcept {
        return (value << n) | (value >> (32 - n));
    }
    static u32 word(const u8* at) noexcept {
        return u32(at[0]) | (u32(at[1]) << 8) | (u32(at[2]) << 16) | (u32(at[3]) << 24);
    }
    static u32 stripe(u32 acc, u32 value) noexcept {
        return rotate(acc + value * B, 13) * A;
    }
public:
    explicit Hash32(u32 seed = 0) noexcept : seed_(seed) {}

    void update(const void* source, std::size_t count) noexcept {
        if (count > bytes_.size() - used_) std::terminate();
        if (count) std::memcpy(bytes_.data() + used_, source, count);
        used_ += count;
    }

    u32 digest() const noexcept {
        const u8* data = bytes_.data();
        std::size_t offset = 0;
        u32 hash;
        if (used_ >= 16) {
            u32 lanes[4] = {seed_ + A + B, seed_ + B, seed_, seed_ - A};
            for (; offset + 16 <= used_; offset += 16)
                for (unsigned lane = 0; lane < 4; ++lane)
                    lanes[lane] = stripe(lanes[lane], word(data + offset + 4 * lane));
            hash = rotate(lanes[0], 1) + rotate(lanes[1], 7)
                 + rotate(lanes[2], 12) + rotate(lanes[3], 18);
        } else {
            hash = seed_ + E;
        }
        hash += static_cast<u32>(used_);
        for (; offset + 4 <= used_; offset += 4)
            hash = rotate(hash + word(data + offset) * C, 17) * D;
        for (; offset < used_; ++offset)
            hash = rotate(hash + u32(data[offset]) * E, 11) * A;
        hash ^= hash >> 15; hash *= B;
        hash ^= hash >> 13; hash *= C;
        return hash ^ (hash >> 16);
    }

    static u32 oneshot(const void* source, std::size_t count, u32 seed = 0) noexcept {
        Hash32 state(seed);
        state.update(source, count);
        return state.digest();
    }
};
}
