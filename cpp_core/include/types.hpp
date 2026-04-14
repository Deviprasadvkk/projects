#pragma once

#include <array>
#include <cstdint>

namespace bharat_alpha
{

    constexpr double kNseTickSize = 0.05;
    constexpr std::size_t kBookDepth = 10;

    struct PriceLevel
    {
        double price;
        std::uint32_t qty;
    };

    struct OrderBookSnapshot
    {
        std::array<PriceLevel, kBookDepth> bids;
        std::array<PriceLevel, kBookDepth> asks;
        std::uint64_t exch_ts_ns;
    };

    struct OrderRequest
    {
        std::uint64_t client_order_id;
        char symbol[16];
        bool is_buy;
        double price;
        std::uint32_t qty;
        std::uint64_t strategy_ts_ns;
    };

    struct RiskDecision
    {
        bool accepted;
        const char *reason;
    };

    struct AlphaSignal
    {
        char symbol[16];
        float price_flip_prob;
        std::int8_t direction;
        std::uint64_t model_ts_ns;
    };

} // namespace bharat_alpha
