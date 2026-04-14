#pragma once

#include <cstdint>
#include <cstring>
#include <vector>

#include "types.hpp"

namespace bharat_alpha
{

#pragma pack(push, 1)
    struct MockTbtPacket
    {
        char symbol[16];
        std::uint64_t exch_ts_ns;
        double bid_px[10];
        std::uint32_t bid_qty[10];
        double ask_px[10];
        std::uint32_t ask_qty[10];
    };
#pragma pack(pop)

    inline OrderBookSnapshot decode_tbt_packet(const MockTbtPacket &pkt)
    {
        OrderBookSnapshot snap{};
        snap.exch_ts_ns = pkt.exch_ts_ns;
        for (std::size_t i = 0; i < kBookDepth; ++i)
        {
            snap.bids[i] = PriceLevel{pkt.bid_px[i], pkt.bid_qty[i]};
            snap.asks[i] = PriceLevel{pkt.ask_px[i], pkt.ask_qty[i]};
        }
        return snap;
    }

    inline MockTbtPacket make_mock_tbt_packet(const char *symbol, double mid, std::uint64_t ts_ns)
    {
        MockTbtPacket pkt{};
        std::memset(&pkt, 0, sizeof(pkt));
        std::strncpy(pkt.symbol, symbol, sizeof(pkt.symbol) - 1);
        pkt.exch_ts_ns = ts_ns;
        for (std::size_t i = 0; i < kBookDepth; ++i)
        {
            const double d = static_cast<double>(i + 1) * kNseTickSize;
            pkt.bid_px[i] = mid - d;
            pkt.ask_px[i] = mid + d;
            pkt.bid_qty[i] = 100 + static_cast<std::uint32_t>(i * 10);
            pkt.ask_qty[i] = 120 + static_cast<std::uint32_t>(i * 10);
        }
        return pkt;
    }

} // namespace bharat_alpha
