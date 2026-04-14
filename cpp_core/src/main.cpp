#include <chrono>
#include <cstring>
#include <iomanip>
#include <iostream>

#include "lob.hpp"
#include "risk.hpp"
#include "tbt_mock.hpp"
#include "types.hpp"
#include "vwap_simd.hpp"

using namespace bharat_alpha;

int main()
{
    const auto pkt = make_mock_tbt_packet("RELIANCE", 2500.0, 1713075900000000000ULL);
    const auto snap = decode_tbt_packet(pkt);

    NseLimitOrderBook lob;
    lob.update(snap);

    SymbolRiskConfig cfg{};
    cfg.ref_price = 2500.0;
    cfg.lower_circuit = 2250.0;
    cfg.upper_circuit = 2750.0;
    cfg.max_order_qty = 50000;
    cfg.fat_finger_bps = 150.0;
    cfg.initial_margin_rate = 0.20;

    RiskManager risk(cfg);
    AccountState account{};
    account.free_cash = 5000000.0;

    OrderRequest order{};
    order.client_order_id = 1;
    std::strncpy(order.symbol, "RELIANCE", sizeof(order.symbol) - 1);
    order.is_buy = true;
    order.price = lob.snapshot().asks[0].price;
    order.qty = 100;
    order.strategy_ts_ns = 1713075900000000200ULL;

    const auto decision = risk.pre_trade_check(order, account);

    const double bid_vwap = vwap_top10_simd(lob.snapshot().bids);
    const double ask_vwap = vwap_top10_simd(lob.snapshot().asks);
    const auto ns_per_call = benchmark_vwap_ns(lob.snapshot().bids, 20000);

    std::cout << "Bharat-Alpha Core Demo\n";
    std::cout << "risk_decision: " << (decision.accepted ? "ACCEPT" : "REJECT")
              << " (" << decision.reason << ")\n";
    std::cout << std::fixed << std::setprecision(4);
    std::cout << "bid_vwap_top10: " << bid_vwap << "\n";
    std::cout << "ask_vwap_top10: " << ask_vwap << "\n";
    std::cout << "simd_vwap_ns: " << ns_per_call << " ns/call\n";

    if (ns_per_call <= 500)
    {
        std::cout << "latency_target_vwap: PASS (< 500 ns)\n";
    }
    else
    {
        std::cout << "latency_target_vwap: CHECK (optimize further)\n";
    }

    return 0;
}
