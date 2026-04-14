#pragma once

#include <cmath>
#include <cstdint>
#include <string>
#include <unordered_map>

#include "types.hpp"

namespace bharat_alpha
{

    struct SymbolRiskConfig
    {
        double ref_price;
        double lower_circuit;
        double upper_circuit;
        std::uint32_t max_order_qty;
        double fat_finger_bps;
        double initial_margin_rate;
    };

    struct AccountState
    {
        double free_cash;
        std::unordered_map<std::string, std::int32_t> net_positions;
    };

    class RiskManager
    {
    public:
        explicit RiskManager(SymbolRiskConfig cfg) : cfg_(cfg) {}

        RiskDecision pre_trade_check(const OrderRequest &req, const AccountState &account) const
        {
            if (req.qty == 0 || req.qty > cfg_.max_order_qty)
            {
                return {false, "fat-finger qty check failed"};
            }

            if (req.price < cfg_.lower_circuit || req.price > cfg_.upper_circuit)
            {
                return {false, "circuit filter breach"};
            }

            const double deviation_bps = std::abs(req.price - cfg_.ref_price) / cfg_.ref_price * 10000.0;
            if (deviation_bps > cfg_.fat_finger_bps)
            {
                return {false, "fat-finger price deviation"};
            }

            const double notional = req.price * static_cast<double>(req.qty);
            const double required_margin = notional * cfg_.initial_margin_rate;
            if (required_margin > account.free_cash)
            {
                return {false, "insufficient margin"};
            }

            return {true, "accepted"};
        }

    private:
        SymbolRiskConfig cfg_;
    };

} // namespace bharat_alpha
