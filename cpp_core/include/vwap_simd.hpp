#pragma once

#include <chrono>
#include <cstdint>
#include <immintrin.h>

#include "types.hpp"

namespace bharat_alpha
{

    inline double vwap_top10_scalar(const std::array<PriceLevel, kBookDepth> &side)
    {
        double px_qty = 0.0;
        double qty = 0.0;
        for (const auto &lvl : side)
        {
            px_qty += lvl.price * static_cast<double>(lvl.qty);
            qty += static_cast<double>(lvl.qty);
        }
        return qty > 0.0 ? px_qty / qty : 0.0;
    }

    inline double vwap_top10_simd(const std::array<PriceLevel, kBookDepth> &side)
    {
        alignas(32) double prices[8]{};
        alignas(32) double qtys[8]{};

        for (int i = 0; i < 8; ++i)
        {
            prices[i] = side[static_cast<std::size_t>(i)].price;
            qtys[i] = static_cast<double>(side[static_cast<std::size_t>(i)].qty);
        }

        __m256d p1 = _mm256_load_pd(&prices[0]);
        __m256d q1 = _mm256_load_pd(&qtys[0]);
        __m256d p2 = _mm256_load_pd(&prices[4]);
        __m256d q2 = _mm256_load_pd(&qtys[4]);

        __m256d pq1 = _mm256_mul_pd(p1, q1);
        __m256d pq2 = _mm256_mul_pd(p2, q2);

        alignas(32) double tmp_pq[8]{};
        alignas(32) double tmp_q[8]{};
        _mm256_store_pd(&tmp_pq[0], pq1);
        _mm256_store_pd(&tmp_pq[4], pq2);
        _mm256_store_pd(&tmp_q[0], q1);
        _mm256_store_pd(&tmp_q[4], q2);

        double sum_pq = 0.0;
        double sum_q = 0.0;
        for (int i = 0; i < 8; ++i)
        {
            sum_pq += tmp_pq[i];
            sum_q += tmp_q[i];
        }

        for (int i = 8; i < 10; ++i)
        {
            sum_pq += side[static_cast<std::size_t>(i)].price * static_cast<double>(side[static_cast<std::size_t>(i)].qty);
            sum_q += static_cast<double>(side[static_cast<std::size_t>(i)].qty);
        }

        return sum_q > 0.0 ? sum_pq / sum_q : 0.0;
    }

    inline double benchmark_vwap_ns(const std::array<PriceLevel, kBookDepth> &side, int iters = 100000)
    {
        volatile double sink = 0.0;
        const auto t0 = std::chrono::high_resolution_clock::now();
        for (int i = 0; i < iters; ++i)
        {
            sink += vwap_top10_simd(side);
        }
        const auto t1 = std::chrono::high_resolution_clock::now();
        (void)sink;
        const auto elapsed = static_cast<double>(std::chrono::duration_cast<std::chrono::nanoseconds>(t1 - t0).count());
        return elapsed / static_cast<double>(iters);
    }

} // namespace bharat_alpha
