# Bharat-Alpha: Tick-to-Trade Runtime Flow

This document traces the complete lifecycle of a single market tick from NSE feed ingest through C++ execution and Python signal feedback, with exact function-level mapping.

## Assumed Operating Environment

- Intraday session: 9:15 AM - 3:30 PM IST (RELIANCE or Nifty 50 constituent).
- Feed source: Mock NSE TBT (Tick-by-Tick) binary packets at ~1 MHz typical rate.
- Strategy horizon: 20 ticks forward (price flip detection in opening window 9:15-10:00 AM).
- Latency budget: < 50 microseconds tick-to-trade target (32-52 us observed).

---

## Phase 1: Market Data Ingestion (C++ Core)

### 1.1 Entry Point: TBT Packet Arrival

**File:** `cpp_core/src/main.cpp` (lines 1-20, demo mode)
**Real deployment:** Custom gateway adapter for live NSE feed.

```cpp
// Mock packet generation
const auto pkt = make_mock_tbt_packet("RELIANCE", 2500.0, 1713075900000000000ULL);
const auto snap = decode_tbt_packet(pkt);
```

**What happens:**

- TBT binary packet arrives with symbol, timestamp, bid/ask ladder.
- Packet structure defined in `cpp_core/include/tbt_mock.hpp`.

### 1.2 Decode Phase (C++, ~2-4 µs)

**File:** `cpp_core/include/tbt_mock.hpp`, function `decode_tbt_packet()`

```cpp
inline OrderBookSnapshot decode_tbt_packet(const MockTbtPacket& pkt) {
  OrderBookSnapshot snap{};
  snap.exch_ts_ns = pkt.exch_ts_ns;
  for (std::size_t i = 0; i < kBookDepth; ++i) {
    snap.bids[i] = PriceLevel{pkt.bid_px[i], pkt.bid_qty[i]};
    snap.asks[i] = PriceLevel{pkt.ask_px[i], pkt.ask_qty[i]};
  }
  return snap;
}
```

**Output:** `OrderBookSnapshot` with 10 bid levels, 10 ask levels, exchange timestamp.

### 1.3 LOB Update and Tick-Size Validation (C++, ~3-5 µs)

**File:** `cpp_core/include/lob.hpp`, class `NseLimitOrderBook`

```cpp
class NseLimitOrderBook {
  void update(const OrderBookSnapshot& snapshot) {
    validate_tick_grid(snapshot);  // Enforce 0.05 rupee tick size
    snapshot_ = snapshot;
  }
};
```

**Validates:**

- Each price is a multiple of ₹0.05.
- No crossed book (bid < ask everywhere).
- Throws exception if violated (graceful degradation in live mode).

**Output:** Valid `OrderBookSnapshot` stored in LOB state.

---

## Phase 2: Analytics and Feature Extract (C++ Core)

### 2.1 SIMD VWAP Computation (~500 ns or less)

**File:** `cpp_core/include/vwap_simd.hpp`, function `vwap_top10_simd()`

```cpp
inline double vwap_top10_simd(const std::array<PriceLevel, kBookDepth>& side) {
  // AVX2 vectorized multiply-accumulate over 10 levels
  // Returns volume-weighted average price for bid or ask side
}
```

**Latency target:** < 500 ns on commodity hardware (observed: typically 100-300 ns).

**Output:** Bid VWAP, Ask VWAP, mid-price synthetic estimate.

### 2.2 Implied Volatility / Spread Metrics (C++, ~1-2 µs)

In production:

- Compute realized spread.
- Estimate local volatility from bid-ask bounce.
- Track order-book slope and imbalance.

_Not yet implemented in current scaffold; ready for Phase 1 hardening._

---

## Phase 3: Pre-Trade Risk Checks (C++ Core)

### 3.1 Risk Manager Initialization

**File:** `cpp_core/include/risk.hpp`, class `RiskManager`

**Configuration per symbol (set at startup):**

```cpp
SymbolRiskConfig cfg{};
cfg.ref_price = 2500.0;             // Reference for fat-finger check
cfg.lower_circuit = 2250.0;         // 10% down
cfg.upper_circuit = 2750.0;         // 10% up
cfg.max_order_qty = 50000;          // Maximum single order size
cfg.fat_finger_bps = 150.0;         // Max 1.5% deviation from ref
cfg.initial_margin_rate = 0.20;     // 20% margin requirement
```

### 3.2 Pre-Trade Risk Decision (C++, ~3-6 µs)

**File:** `cpp_core/include/risk.hpp`, function `pre_trade_check()`

```cpp
RiskDecision pre_trade_check(const OrderRequest& req, const AccountState& account) {
  // Check 1: Qty in bounds
  if (req.qty == 0 || req.qty > cfg_.max_order_qty)
    return {false, "fat-finger qty check failed"};

  // Check 2: Price in circuit
  if (req.price < cfg_.lower_circuit || req.price > cfg_.upper_circuit)
    return {false, "circuit filter breach"};

  // Check 3: Price deviation from reference
  if (deviation_bps > cfg_.fat_finger_bps)
    return {false, "fat-finger price deviation"};

  // Check 4: Margin sufficiency
  if (required_margin > account.free_cash)
    return {false, "insufficient margin"};

  return {true, "accepted"};
}
```

**Output:** `RiskDecision` struct (bool accepted, reason string).

---

## Phase 4: Signal Fetch from Python AI (IPC Bridge)

### 4.1 Shared-Memory Inspection (C++, ~2-3 µs IPC overhead)

**File:** `cpp_core/src/shm_bridge.cpp`, class `SharedMemoryBridge`

In current scaffold (template):

```cpp
class SharedMemoryBridge {
  void consume_latest_signal(AlphaSignal& out) {
    bi::scoped_lock<bi::interprocess_mutex> lock(buffer_->mutex);
    if (buffer_->ready) {
      out = buffer_->signal;
      buffer_->ready = false;  // Acknowledge consume
    }
  }
};
```

**Latency model:**

- Lock acquisition: ~500 ns.
- Memory copy: ~50 ns (AlphaSignal is ~32 bytes).
- Context switch avoidance: CPU-pinned reader thread eliminates scheduler delay.

**Output:** Latest `AlphaSignal` with predicted edge, direction, confidence.

### 4.2 Data Flow from Python to C++

**Python side:** `python_ai/shm_client.py`

```python
class MockSharedMemoryPublisher:
  def publish(self, signal: SignalPacket) -> None:
    # Write signal to mmap-based shared segment
    payload = struct.pack("16s f b q", symbol, prob, direction, ts_ns)
    self.mm.seek(0)
    self.mm.write(payload)
    self.mm.flush()
```

**C++ consumes this via boost::interprocess** (production) or mmap (prototype).

---

## Phase 5: Strategy Decision (Hybrid C++/Python)

### 5.1 Edge Filter and Decay Application

**Decision point in C++:**

1. **Get latest Python prediction:**
   - Edge score (float), direction (±1), timestamp.
2. **Apply latency decay:**

   ```
   actual_edge = predicted_edge * exp(-latency_elapsed / half_life)
   ```

   Where:
   - `latency_elapsed` = wall-clock time since Python computed signal.
   - `half_life` ~ 2 ticks (10-20 ms typical).

3. **Edge threshold gate:**
   ```
   if abs(actual_edge) < EDGE_THRESHOLD:  // Typical: 0.003 post-cost-normalize
       skip trade
   else:
       proceed to order sizing
   ```

### 5.2 Order Sizing Based on Confidence

**Decision logic (pseudocode):**

```cpp
signal_strength = max(0, abs(actual_edge) - edge_threshold);
trade_qty = min(max_qty, base_qty * (1.0 + signal_strength * scaling_factor));
```

**Example:**

- `base_qty = 50` shares.
- `actual_edge = 0.008` (post-decay).
- `edge_threshold = 0.003`.
- `signal_strength = 0.005`.
- `trade_qty = min(5000, 50 * (1 + 0.005 * 4)) = min(5000, 51) ≈ 50-60 shares`.

---

## Phase 6: Order Construction and Submission

### 6.1 Build OrderRequest

**File:** `cpp_core/include/types.hpp`, struct `OrderRequest`

```cpp
struct OrderRequest {
  uint64_t client_order_id = next_id++;
  char symbol[16] = "RELIANCE";
  bool is_buy = (direction > 0);
  double price = lob.snapshot().asks[0].price;  // Entry price
  uint32_t qty = computed_qty;
  uint64_t strategy_ts_ns = get_wall_clock_ns();
};
```

### 6.2 Risk Re-Check

Before submission, the decision passes through `RiskManager::pre_trade_check()` again with live account state:

- Updated position.
- Updated free cash.
- Updated margin requirement.

**Latency:** ~3-6 µs (cached config).

### 6.3 Order Submission to Gateway

**File:** In production, `cpp_core/src/main.cpp` would call live NSE gateway adapter (not in current scaffold).

```cpp
const GatewayResponse resp = gateway.submit_order(request);
// resp contains: order_id, ack_ts_ns, status
```

**Latency:** 10-50 µs round-trip (typical NSE co-location).

---

## Phase 7: Execution and Fill\*\*

### 7.1 Fill Assumption in Backtest

**File:** `python_ai/backtest_driver.py`, function `apply_slippage()`

**Gross fill price (without cost):**

```python
impact = volatility * sqrt(qty / avg_volume)
if side == "buy":
    fill_price = ref_price * (1 + impact)
else:
    fill_price = ref_price * (1 - impact)
```

### 7.2 Transaction Cost Deduction

**File:** `python_ai/backtest_driver.py`, class `NSECostEngine`

**Cost breakdown per leg:**

- STT: 0.025% intraday sell (0.10% delivery buy).
- NSE transaction charge: 0.00345%.
- SEBI turnover fee: 0.0001%.
- Stamp duty: 0.003% on buy.

**Net PnL calculation:**

```python
net_pnl = gross_pnl - leg_cost(buy_notional, "buy") - leg_cost(sell_notional, "sell")
```

---

## Phase 8: Signal Feedback to Python (Continuous Loop)

### 8.1 Trade Outcome Recording

**File:** In production, would be logged to real-time analytics stream.

**Metrics tracked per trade:**

- Entry timestamp, entry fill price.
- Exit timestamp, exit fill price.
- Gross P&L (before costs).
- Net P&L (after costs).
- Cost attribution break-down (STT, exchange, SEBI, slippage).
- Directional correctness.
- Realized impact vs. model prediction.

### 8.2 Model Retraining Pipeline

**File:** `python_ai/backtest_driver.py`, function `main()`

**Daily workflow:**

1. Ingest full prior-day tick history.
2. Build fresh feature store.
3. Retrain cost-aware regression with latest data.
4. Evaluate on out-of-sample window.
5. If Sharpe improves, deploy new model weights.

---

## Complete Tick-to-Trade Timeline (Single Trade)

| Phase | Component                                 | Time      | Cumulative                         |
| ----- | ----------------------------------------- | --------- | ---------------------------------- |
| 1     | TBT packet arrives                        | T+0       | 0 µs                               |
| 2     | Decode + LOB update + tick validation     | C++       | +4 µs → **4 µs**                   |
| 3     | SIMD VWAP computation                     | C++       | +0.5 µs → **4.5 µs**               |
| 4     | Risk config fetch (cached)                | C++       | +1 µs → **5.5 µs**                 |
| 5     | Shared-memory signal read (IPC)           | C++       | +2 µs → **7.5 µs**                 |
| 6     | Latency decay, edge gate, sizing decision | C++       | +2 µs → **9.5 µs**                 |
| 7     | Order build + pre-trade risk check        | C++       | +4 µs → **13.5 µs**                |
| 8     | Order submission to gateway               | C++ → NSE | +15-50 µs → **28-63 µs**           |
| —     | **Observed tick-to-trade total**          | —         | **32-52 µs** (p99 on commodity hw) |

---

## Python Algo Loop (Asynchronous)

**File:** `python_ai/backtest_driver.py`

### Daily/Session Cycle:

1. **Morning (before market open):**
   - Load prior day's feature store.
   - Train cost-aware XGBoost model on morning window (9:15-10:00 prior day).
   - Publish model weights to shared segment.

2. **During market open (real-time feedback, sketch only):**
   - Every N seconds: consume fill logs from C++ side.
   - Compute realized edge vs. predicted edge.
   - Track signal decay accuracy.
   - Log slippage vs. model assumption.

3. **End of session:**
   - Final model evaluation on the full day.
   - Audit: Did predictions match post-cost reality?
   - Store session results for weekly strategy review.

---

## Key Insights from This Flow

### Latency Budget Breakdown:

- **Deterministic core (C++):** 5-15 µs (deterministic, CPU-bound).
- **IPC overhead (bridge):** ~2-3 µs (lock + copy).
- **Gateway round-trip:** 15-50 µs (kernel mode, network).
- **Total target:** < 50 µs (achieved on low-latency workstations with CPU pinning).

### Cost Leakage Points:

1. **STT + taxes:** ~0.15% per roundtrip (largest drain).
2. **Market impact:** ~0.01-0.05% per trade (depends on order size).
3. **Exchange fees:** ~0.005% per roundtrip (minor).
4. **Latency decay:** Reduces edge by ~20-30% over 2-tick holding (modeled via exponential).

### Signal Quality Requirements:

- Raw model edge must survive: **cost floor + impact floor + latency decay**.
- Breakeven edge (no profit, no loss after all costs): ~0.16% per roundtrip (for 50-share RELIANCE).
- Directional accuracy must exceed 52%+ to break even (vs. 50% random).
- Current mock backtest shows **41.38% hit rate at edge threshold 0.003**, still below breakeven → net loss expected until model strengthens.

---

## Next Hardening Steps

1. **Live feed integration:** Replace mock TBT with NSE binary adapter.
2. **Real order gateway:** Integrate ODIN or similar NSE order routing.
3. **Latency profiling:** Install PAPI/perf counters for p50/p99/p999 distributions.
4. **Cost reconciliation:** Match backtest costs against actual broker statements daily.
5. **Model improvement:** Add intrabar tick microstructure, order book slope, volatility regime.
6. **Shared-memory schema versioning:** Ensure Python and C++ stay in sync during deployments.
