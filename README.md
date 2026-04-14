# Bharat-Alpha: HFT for Indian Equities (NSE)

Bharat-Alpha is a two-engine high-frequency trading project:

- A C++ low-latency core for deterministic market handling, risk checks, and fast execution logic.
- A Python intelligence layer for AI signal generation and feature engineering over NSE-style data.

This scaffold is built to demonstrate architecture and implementation patterns for a sub-50 microsecond tick-to-trade target on commodity hardware.

## Project Layout

```
cpp_core/
  CMakeLists.txt
  include/
    types.hpp
    lob.hpp
    risk.hpp
    vwap_simd.hpp
    tbt_mock.hpp
  src/
    main.cpp
    shm_bridge.cpp
python_ai/
  requirements.txt
  feature_store.py
  alpha_model.py
  backtest_driver.py
  shm_client.py
docs/
  architecture.md
  roadmap.md
  tick_to_trade_flow.md
```

## Quick Start

### C++ Core

```powershell
cd cpp_core
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
./build/bharat_alpha_core
```

### Python Intelligence

```powershell
cd python_ai
../.venv/Scripts/python.exe -m pip install -r requirements.txt
../.venv/Scripts/python.exe backtest_driver.py
```

## Notes

- NSE tick size is modeled as Rs 0.05 and enforced by the C++ LOB module.
- SEBI-style pre-trade controls are implemented in `RiskManager`.
- SIMD VWAP over top 10 levels is implemented with AVX2 and benchmarked in the core.
- Shared-memory IPC design is provided via Boost.Interprocess bridge components.

## Documentation

- **[Architecture](docs/architecture.md)**: System design, components, and integration points.
- **[Roadmap](docs/roadmap.md)**: Implementation and hardening phases.
- **[Tick-to-Trade Flow](docs/tick_to_trade_flow.md)**: Step-by-step runtime trace from market data ingest through execution, with exact function-level mapping and latency budget breakdown.
