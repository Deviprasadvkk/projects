# Bharat-Alpha Technical Architecture

## 1) C++ Low-Latency Core (The Symphony)

### 1.1 Event Pipeline

1. TBT packet decode (`tbt_mock.hpp`) into `OrderBookSnapshot`.
2. LOB update with NSE tick-grid enforcement (`lob.hpp`, Rs 0.05).
3. SIMD analytics for top-10 level VWAP (`vwap_simd.hpp`).
4. Pre-trade risk checks (`risk.hpp`) for fat-finger, margin, circuit filters.
5. Order decision + execution path (in `main.cpp`, replaceable with live gateway).

### 1.2 Core Components

- `NseLimitOrderBook`: validates monotonic and non-crossed book with tick-size checks.
- `RiskManager`: enforces SEBI-style controls:
  - Max order quantity (fat-finger)
  - Price deviation from reference (fat-finger)
  - Initial margin sufficiency
  - Circuit filter bounds
- `vwap_top10_simd`: AVX2 vectorized VWAP for 10 levels.
- `SharedMemoryBridge` (`shm_bridge.cpp`): Boost.Interprocess publisher for AI signals.

### 1.3 Latency Budget (Target < 50 us Tick-to-Trade)

- TBT parse + normalization: 4-8 us
- LOB update + feature extraction: 6-10 us
- Risk checks: 3-6 us
- Strategy + order build: 4-8 us
- Gateway handoff + serialization: 15-20 us

Expected total: 32-52 us, requiring CPU pinning, huge pages, and lock-free queues in production.

## 2) Python Intelligence (The Strategist)

### 2.1 Feature Store

Implemented in `feature_store.py`:

- Market microstructure features: `ret_1`, `ret_5`, rolling volatility
- NSE domain signals:
  - Delivery Percentage
  - Sector-wise Rotation z-score
- Daily parquet persistence for reproducible research

### 2.2 AI Alpha Model

Implemented in `alpha_model.py`:

- Primary model: XGBoost classifier (fallback to sklearn gradient boosting)
- Label: Price Flip event over configurable horizon in bps
- Focus window: 9:15 AM to 10:00 AM for opening volatility

### 2.3 Research Loop

`backtest_driver.py`:

- Generates mock NSE-like intraday data
- Builds feature set
- Trains and evaluates Price Flip classifier
- Outputs report for rapid iteration

## 3) Connectivity Layer

### 3.1 Shared Memory Contract

- C++ side: Boost.Interprocess shared segment with condition variable
- Python side: prototype publisher (mmap) and schema-compatible packet
- Message schema:
  - symbol (16 bytes)
  - price_flip_prob (float)
  - direction (int8)
  - model_ts_ns (int64)

### 3.2 Why Shared Memory

- Eliminates TCP/UDP stack jitter and kernel socket overhead
- Enables deterministic sub-10 us IPC transfer in single-host deployment

## 4) Production Hardening Next

- Replace demo loops with lock-free ring buffer per symbol shard
- NUMA-aware thread pinning for feed handler, risk, and execution lanes
- Zero-copy binary decoder for real NSE TBT captures
- Deterministic replay harness and p99/p999 latency dashboards
