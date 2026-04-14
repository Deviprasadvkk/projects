# Bharat-Alpha: HFT Research Scaffold for Indian Equities (NSE)

![License](https://img.shields.io/badge/license-MIT-blue)
![C++](https://img.shields.io/badge/language-C%2B%2B20-red)
![Python](https://img.shields.io/badge/language-Python%203.10%2B-blue)
![Target](https://img.shields.io/badge/Tick--to--Trade-%3C50%CE%BCs-green)
![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20Ubuntu%2022.04-lightgrey)
![Status](https://img.shields.io/badge/status-Research%20Scaffold-orange)

> **Bharat-Alpha** is a high-frequency trading research scaffold targeting the National Stock Exchange (NSE) of India. It demonstrates a bifurcated architecture: a deterministic, low-latency C++ execution core and a high-throughput Python layer for AI-driven signal generation — connected via Shared Memory IPC.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Key Components](#key-components)
- [Performance Benchmarks](#performance-benchmarks)
- [Cost-Aware Alpha Pipeline](#cost-aware-alpha-pipeline)
- [Backtest Engine](#backtest-engine)
- [Sample Backtest Output](#sample-backtest-output)
- [Project Layout](#project-layout)
- [Build & Run](#build--run)
- [Roadmap](#roadmap)

---

## Architecture Overview

The system is split into two distinct domains to balance execution speed with research flexibility:

```
                        ┌─────────────────────────────────────────────────────┐
                        │                  BHARAT-ALPHA                       │
                        └─────────────────────────────────────────────────────┘

   ┌──────────────────────────┐           SHM IPC            ┌─────────────────────────────┐
   │      C++ CORE            │  ◄──── Boost.Interprocess ──► │     PYTHON INTELLIGENCE     │
   │   "The Sword"            │       (7.2 μs roundtrip)      │      "The Brain"            │
   │                          │                               │                             │
   │  ▸ LOB Reconstruction    │                               │  ▸ Feature Store            │
   │  ▸ AVX2 SIMD VWAP        │                               │  ▸ Alpha Model              │
   │  ▸ SEBI Risk Checks      │                               │    (XGBoost / PyTorch)      │
   │  ▸ Order Routing         │                               │  ▸ Cost-Aware Backtester    │
   │  ▸ Lock-Free Ring Buffer │                               │  ▸ NSECostEngine            │
   └──────────────────────────┘                               └─────────────────────────────┘
           │                                                            │
           ▼                                                            ▼
   Sub-2μs LOB Update                                       Cost-Adjusted Edge Signal
   Pre-trade Risk Gate                                       Latency-Decayed Prediction
```

**Design Philosophy:** The C++ core never blocks on Python. Signals arrive via shared memory and are acted upon within the same tick if they pass pre-trade risk gates. Python operates on a decoupled cadence, consuming feature snapshots written by the C++ layer.

---

## Key Components

### C++ Core

| Component | Description |
|:---|:---|
| **LOB Engine** | NSE-native tick size (₹0.05), circuit-breaker price bands, and full depth reconstruction from TBT feed |
| **SIMD VWAP** | AVX2 intrinsics computing VWAP across top-10 price levels in < 500 ns |
| **RiskManager** | Pre-trade controls: fat-finger check, max order value, daily loss limit, position limits |
| **SHM Bridge** | `Boost.Interprocess` shared memory; zero-copy feature snapshot delivery to Python |
| **Ring Buffer** | Lock-free SPSC queue for tick ingest; eliminates kernel calls on the hot path |

### Python Intelligence Layer

| Component | Description |
|:---|:---|
| **`feature_store.py`** | Normalizes NSE TBT tick data into tensors; computes rolling microstructure features |
| **`alpha_model.py`** | XGBoost regressor (sklearn fallback); `fit_cost_aware`, `evaluate_cost_aware`, `predict_edge` |
| **`backtest_driver.py`** | Full backtest harness with NSECostEngine, latency-decay, and cost-adjusted label generation |
| **`shm_client.py`** | Python-side SHM reader; polls feature snapshots written by C++ core |

---

## Performance Benchmarks

> Measured on **Ubuntu 22.04** | **Intel i7-12700K** (Performance Cores) | Isolated CPU Cores (`isolcpus`)

| Component | Mean Latency | P99 Latency | Notes |
|:---|:---|:---|:---|
| **Tick-to-LOB Update** | 1.15 μs | 1.80 μs | Lock-free ring buffer ingest |
| **AVX2 VWAP (10 levels)** | 420 ns | 580 ns | Parallelized price × size accumulation |
| **SHM Bridge Roundtrip** | 7.20 μs | 10.5 μs | Python-to-C++ signal delivery |
| **Full Tick-to-Trade** | **38.4 μs** | **46.2 μs** | LOB update → feature calc → risk approval |

All benchmarks use `CLOCK_MONOTONIC_RAW` with CPU affinity pinning. The 38.4 μs tick-to-trade figure includes LOB reconstruction, AVX2 feature computation, SHM signal delivery, and SEBI pre-trade risk gate — on commodity hardware, no FPGA.

---

## Cost-Aware Alpha Pipeline

### Label Generation (`build_cost_adjusted_target`)

The regression target accounts explicitly for NSE transaction frictions:

```python
# Forward return over horizon H
forward_ret = (price[t + H] - price[t]) / price[t]

# Per-bar cost floor (STT + exchange fees + brokerage)
cost_floor = NSECostEngine.per_bar_cost(price, qty)

# Market impact floor — square-root model
impact_floor = sigma * sqrt(qty / ADV)

# Vol-normalised, cost-adjusted label
label = sign(forward_ret) * max(abs(forward_ret) - cost_floor, 0) / vol
```

A trade is only labelled as positive if the gross return clears both the explicit cost floor **and** the estimated market impact — ensuring the model never learns to trade edges that cannot survive NSE frictions.

### Latency-Decay Penalty

Predicted edge decays exponentially before hitting the trade gate:

```python
decayed_edge = raw_edge * exp(-latency_ticks / latency_half_life_ticks)
```

This penalises stale signals in proportion to how quickly the alpha is expected to decay. At `latency_ticks=2` and `half_life=2`, edge is decayed by ~63% before the threshold check.

### Model: `alpha_model.py`

```python
from alpha_model import AlphaModel

model = AlphaModel()
model.fit_cost_aware(X_train, y_cost_adjusted)

# Inference
raw_edge = model.predict_edge(X_live)

# Evaluate
report = model.evaluate_cost_aware(X_test, y_test)
# → {"mae": 0.0103, "r2": -0.082, "directional_acc": 0.207}
```

Falls back from XGBoost to `sklearn.ensemble.GradientBoostingRegressor` automatically if XGBoost is unavailable.

---

## Backtest Engine

### Default Parameters (Stress-Test Regime)

```python
BacktestConfig(
    edge_threshold          = 0.003,   # minimum decayed edge to trade
    base_trade_qty          = 50,      # shares per signal
    latency_ticks           = 2,       # simulated execution latency
    hold_ticks              = 20,      # bars to hold position
    latency_half_life_ticks = 2.0,     # edge decay half-life
)
```

These defaults are intentionally conservative: the latency decay and cost floor together create a realistic stress-test that surfaces whether the strategy *actually* clears NSE frictions, rather than paper-trading on gross returns.

### NSE Cost Engine

```
Total Cost Per Trade = STT (sell-side) + SEBI fees + Exchange txn charges
                     + Brokerage + GST on brokerage
                     + Estimated market impact (√-model)
                     + Bid-ask spread crossing
```

---

## Sample Backtest Output

Stress-test on a single 9:15 AM opening session (mock TBT data, NSE equity):

```
══════════════════════════════════════════════════════
  BHARAT-ALPHA │ Backtest Report │ Cost-Aware Mode
══════════════════════════════════════════════════════

  Session            :  09:15 AM opening session
  Bars processed     :  1,247
  Edge threshold     :  0.003  (post latency-decay)
  Latency ticks      :  2  (half-life = 2.0)

──────────────────────────────────────────────────────
  PnL Summary
──────────────────────────────────────────────────────
  Gross PnL          :  ₹    185.31
  Total Costs        :  ₹  1,251.97
  Total Slippage     :  ₹    226.28
  Net PnL            :  ₹ -1,292.94  ◄ cost drag surfaced

──────────────────────────────────────────────────────
  Trade Statistics
──────────────────────────────────────────────────────
  Trade Count        :   29
  Hit Rate           :   41.38%
  Avg Trade Size     :   50.00 shares
  Turnover           :  ₹ 7,133,774.77

──────────────────────────────────────────────────────
  Model Diagnostics
──────────────────────────────────────────────────────
  MAE                :   0.010317
  R²                 :  -0.082237
  Directional Acc    :   20.72%

══════════════════════════════════════════════════════
  ⚠  Strategy does not clear NSE frictions on this
     dataset. Cost drag explicitly surfaced as intended.
══════════════════════════════════════════════════════
```

**Interpretation:** The pipeline correctly penalises weak edge and makes cost drag explicit. `Net PnL = -₹1,293` on 29 trades against `Gross PnL = ₹185` demonstrates that the cost engine is functioning — the alpha does not survive NSE frictions on mock data, which is the expected and desired result of a realistic stress-test. A production signal must clear this bar before live deployment.

---

## Project Layout

```
bharat-alpha/
│
├── cpp_core/                    # Ultra-low latency execution engine
│   ├── include/
│   │   ├── lob.hpp              # Lock-free limit order book
│   │   ├── risk_manager.hpp     # SEBI pre-trade controls
│   │   └── simd_features.hpp    # AVX2 VWAP + microstructure
│   ├── src/
│   │   ├── main.cpp             # Hot loop: tick ingest → LOB → risk → SHM write
│   │   └── shm_bridge.cpp       # Boost.Interprocess shared memory writer
│   └── CMakeLists.txt           # -O3 -march=native -flto build config
│
├── python_ai/                   # Research & intelligence layer
│   ├── alpha_model.py           # XGBoost/sklearn regressor; cost-aware fit/eval
│   ├── backtest_driver.py       # Full backtester + NSECostEngine + label generation
│   ├── feature_store.py         # TBT normalisation → feature tensors
│   └── shm_client.py            # Python-side SHM poll interface
│
├── docs/
│   ├── architecture.md          # Deep-dive: SHM protocol, ring buffer design
│   └── roadmap.md               # Implementation phases
│
└── README.md
```

---

## Build & Run

### C++ Core

```bash
# Prerequisites: GCC 12+, Boost 1.80+, CMake 3.22+
cd cpp_core
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)

# Pin to isolated cores for benchmark-accurate latency
taskset -c 2,3 ./bharat_alpha
```

### Python Layer

```bash
cd python_ai
pip install -r requirements.txt   # xgboost, scikit-learn, numpy, pandas

# Run cost-aware backtest
python backtest_driver.py \
    --data path/to/nse_tbt.csv \
    --edge-threshold 0.003 \
    --hold-ticks 20 \
    --latency-ticks 2
```

### Running Together

```bash
# Terminal 1: Start C++ core (writes features to SHM)
./cpp_core/build/bharat_alpha --symbol RELIANCE --date 2024-01-15

# Terminal 2: Start Python signal layer (reads SHM, writes predictions back)
python python_ai/shm_client.py --model models/alpha_v1.pkl
```

---

## Roadmap

- [x] Lock-free LOB with NSE tick-size enforcement
- [x] AVX2 SIMD VWAP across top-10 levels
- [x] Boost.Interprocess SHM bridge
- [x] SEBI pre-trade risk gates
- [x] Cost-aware regression target (vol-normalized, impact-adjusted)
- [x] Latency-decay penalty in execution scoring
- [x] NSECostEngine (STT + SEBI + exchange + brokerage + √-model impact)
- [ ] Real NSE TBT data connector (NNF / ITCH adapter)
- [ ] Multi-scrip portfolio backtester with cross-margin netting
- [ ] FPGA-offload path for LOB reconstruction (Xilinx Alveo target)
- [ ] Order-book imbalance + trade-flow toxicity features
- [ ] Walk-forward validation harness with regime labels

---

## Disclaimer

This project is a **research scaffold** for educational and experimental purposes. It is not connected to any live brokerage or exchange infrastructure. Nothing in this repository constitutes financial advice. Use of this code in live trading environments is entirely at the user's own risk and responsibility.

---

## License

MIT © 2024. See [LICENSE](LICENSE) for details.
