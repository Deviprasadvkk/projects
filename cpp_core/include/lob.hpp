#pragma once

#include <algorithm>
#include <array>
#include <cmath>
#include <stdexcept>

#include "types.hpp"

namespace bharat_alpha
{

    class NseLimitOrderBook
    {
    public:
        void update(const OrderBookSnapshot &snapshot)
        {
            validate_tick_grid(snapshot);
            snapshot_ = snapshot;
        }

        const OrderBookSnapshot &snapshot() const { return snapshot_; }

    private:
        static bool on_tick(double px)
        {
            const double ticks = px / kNseTickSize;
            return std::abs(ticks - std::round(ticks)) < 1e-9;
        }

        static void validate_tick_grid(const OrderBookSnapshot &s)
        {
            for (std::size_t i = 0; i < kBookDepth; ++i)
            {
                if (!on_tick(s.bids[i].price) || !on_tick(s.asks[i].price))
                {
                    throw std::runtime_error("price violates NSE 0.05 tick size");
                }
                if (s.bids[i].price >= s.asks[i].price)
                {
                    throw std::runtime_error("crossed book in snapshot");
                }
            }
        }

        OrderBookSnapshot snapshot_{};
    };

} // namespace bharat_alpha
