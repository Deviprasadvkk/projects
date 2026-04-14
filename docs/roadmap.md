# Bharat-Alpha Roadmap

## Phase 0: Foundation (Week 1)

1. Freeze message schemas and symbol metadata layout.
2. Build deterministic market replay harness.
3. Add CI for C++ and Python modules.

## Phase 1: Low-Latency Core (Weeks 2-4)

1. Implement full depth LOB with incremental update semantics.
2. Integrate complete SEBI-style risk matrix:
   - Price bands and dynamic reference updates
   - Product-specific margin schedules
   - Kill-switch and net exposure clamps
3. Optimize SIMD analytics and add p50/p99 histograms.
4. Add unit and fuzz tests for parser and risk logic.

Milestone: Stable C++ path under 30 us for 1-symbol synthetic load.

## Phase 2: AI Strategist (Weeks 5-7)

1. Build NSE historical ingestion pipeline (tick + bhavcopy + corporate actions).
2. Expand feature store:
   - Delivery shocks
   - Sector rotation momentum
   - Auction and opening imbalance signals
3. Train XGBoost and Transformer baseline models.
4. Add walk-forward validation and leakage checks.

Milestone: Robust Price Flip model with calibrated probabilities in open session.

## Phase 3: Shared-Memory Integration (Weeks 8-9)

1. Finalize Boost.Interprocess bridge with lock-free handoff.
2. Versioned signal schema and backward-compatible readers.
3. Add heartbeat, stale-signal detection, and health probes.

Milestone: End-to-end inference-to-order signal transfer under 10 us p99.

## Phase 4: Tick-to-Trade Optimization (Weeks 10-12)

1. CPU isolation, IRQ tuning, huge pages, and cache-line alignment.
2. Strategy/risk co-location with batched branchless checks.
3. Release-mode profiling and tail-latency elimination.

Milestone: Tick-to-trade < 50 us p99 on standard workstation.

## Phase 5: Research + Ops (Weeks 13+)

1. Unified experiment tracking and model registry.
2. Daily replay backtests against new NSE sessions.
3. Post-trade analytics for slippage, adverse selection, and queue position quality.
4. Governance: risk audit logs and model explainability reports.
