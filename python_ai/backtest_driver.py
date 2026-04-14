from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd

from alpha_model import AlphaModelConfig, PriceFlipAlpha
from feature_store import FeatureStoreConfig, NseFeatureStore


@dataclass
class NSECostEngine:
    intraday: bool = True

    def __post_init__(self) -> None:
        self.stt_rate = 0.00025 if self.intraday else 0.001
        self.exch_charge = 0.0000345
        self.sebi_fees = 0.000001
        self.stamp_duty = 0.00003

    def leg_cost(self, notional: float, side: str) -> float:
        cost = notional * self.exch_charge + notional * self.sebi_fees
        if self.intraday:
            if side == "sell":
                cost += notional * self.stt_rate
        else:
            cost += notional * self.stt_rate
        if side == "buy":
            cost += notional * self.stamp_duty
        return cost

    def calculate_net_pnl(self, gross_pnl: float, buy_notional: float, sell_notional: float) -> float:
        costs = self.leg_cost(buy_notional, "buy") + self.leg_cost(sell_notional, "sell")
        return gross_pnl - costs


def apply_slippage(price: float, size: int, avg_volume: float, daily_volatility: float, side: str) -> float:
    if avg_volume <= 0:
        return price
    impact = daily_volatility * np.sqrt(size / avg_volume)
    impact = float(np.clip(impact, 0.0, 0.10))
    if side == "buy":
        return price * (1.0 + impact)
    return price * (1.0 - impact)


def make_mock_data(n: int = 30000) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(42)
    ts = pd.date_range("2026-04-10 09:15:00", periods=n, freq="s")
    px = 2500 + np.cumsum(rng.normal(0, 0.4, size=n))

    ticks = pd.DataFrame(
        {
            "ts": ts,
            "date": ts.date.astype(str),
            "symbol": "RELIANCE",
            "last_price": px,
            "qty": rng.integers(1, 2000, size=n),
        }
    )

    delivery = pd.DataFrame({"symbol": ["RELIANCE"], "date": [str(ts[0].date())], "delivery_pct": [52.4]})
    sectors = pd.DataFrame({"symbol": ["RELIANCE"], "date": [str(ts[0].date())], "sector_rotation_z": [1.1]})
    return ticks, delivery, sectors


def estimate_daily_volatility(prices: pd.Series) -> float:
    returns = prices.pct_change().dropna()
    if returns.empty:
        return 0.0
    seconds_per_trading_day = 6.5 * 60 * 60
    return float(returns.std(ddof=0) * np.sqrt(seconds_per_trading_day))


def build_cost_adjusted_target(
    df: pd.DataFrame,
    cost_engine: NSECostEngine,
    horizon_ticks: int,
    representative_qty: int,
    avg_daily_volume: float,
    daily_volatility: float,
    vol_floor: float = 1e-4,
) -> pd.Series:
    px = df["last_price"].astype(float)
    forward_ret = (px.shift(-horizon_ticks) / px) - 1.0

    representative_notional = px * float(representative_qty)
    txn_cost = representative_notional.map(lambda n: cost_engine.leg_cost(float(n), "buy") + cost_engine.leg_cost(float(n), "sell"))

    impact_frac = daily_volatility * np.sqrt(max(representative_qty, 1) / max(avg_daily_volume, 1.0))
    impact_frac = float(np.clip(impact_frac, 0.0, 0.10))
    impact_cost = 2.0 * representative_notional * impact_frac

    cost_floor_frac = (txn_cost + impact_cost) / representative_notional.replace(0.0, np.nan)
    cost_floor_frac = cost_floor_frac.fillna(0.0)

    signed_net_ret = np.sign(forward_ret) * np.maximum(np.abs(forward_ret) - cost_floor_frac, 0.0)
    vol_norm = max(daily_volatility, vol_floor)
    target = (signed_net_ret / vol_norm).fillna(0.0)
    return target


def run_cost_aware_backtest(
    data: pd.DataFrame,
    alpha: PriceFlipAlpha,
    feature_cols: List[str],
    cost_engine: NSECostEngine,
    avg_daily_volume: float,
    daily_volatility: float,
    edge_threshold: float = 0.20,
    max_trade_qty: int = 5000,
    base_trade_qty: int = 1000,
    latency_ticks: int = 2,
    hold_ticks: int = 20,
    latency_half_life_ticks: float = 2.0,
) -> dict:
    if data.empty:
        return {}

    signal_frame = data.copy().reset_index(drop=True)
    signal_frame["edge_score"] = alpha.predict_edge(signal_frame, feature_cols)

    trades = []
    gross_pnl = 0.0
    net_pnl = 0.0
    total_buy_notional = 0.0
    total_sell_notional = 0.0
    wins = 0
    losses = 0
    total_costs = 0.0
    total_slippage = 0.0

    for i, row in signal_frame.iterrows():
        raw_edge = float(row["edge_score"])
        decay = float(np.exp(-latency_ticks / max(latency_half_life_ticks, 1e-6)))
        decayed_edge = raw_edge * decay
        if abs(decayed_edge) < edge_threshold:
            continue

        if i + latency_ticks >= len(signal_frame):
            break

        direction = 1.0 if decayed_edge > 0 else -1.0
        signal_strength = max(0.0, abs(decayed_edge) - edge_threshold)
        qty = int(min(max_trade_qty, max(1, base_trade_qty * (1.0 + signal_strength * 4.0))))
        if qty <= 0:
            continue

        entry_idx = i + latency_ticks
        exit_idx = min(i + latency_ticks + hold_ticks, len(signal_frame) - 1)

        entry_ref = float(signal_frame.at[entry_idx, "last_price"])
        exit_ref = float(signal_frame.at[exit_idx, "last_price"])

        entry_side = "buy" if direction > 0 else "sell"
        exit_side = "sell" if direction > 0 else "buy"

        entry_fill = apply_slippage(entry_ref, qty, avg_daily_volume, daily_volatility, entry_side)
        exit_fill = apply_slippage(exit_ref, qty, avg_daily_volume, daily_volatility, exit_side)

        gross_trade_pnl = direction * (exit_ref - entry_ref) * qty
        realized_trade_pnl = direction * (exit_fill - entry_fill) * qty

        buy_notional = entry_fill * qty if direction > 0 else exit_fill * qty
        sell_notional = exit_fill * qty if direction > 0 else entry_fill * qty
        roundtrip_net_pnl = cost_engine.calculate_net_pnl(realized_trade_pnl, buy_notional, sell_notional)

        expected_impact_cost = abs(realized_trade_pnl - gross_trade_pnl)
        roundtrip_costs = cost_engine.leg_cost(buy_notional, "buy") + cost_engine.leg_cost(sell_notional, "sell")

        gross_pnl += gross_trade_pnl
        net_pnl += roundtrip_net_pnl
        total_buy_notional += buy_notional
        total_sell_notional += sell_notional
        total_costs += roundtrip_costs
        total_slippage += expected_impact_cost

        if roundtrip_net_pnl > 0:
            wins += 1
        else:
            losses += 1

        trades.append(
            {
                "entry_idx": entry_idx,
                "exit_idx": exit_idx,
                "direction": direction,
                "qty": qty,
                "edge": decayed_edge,
                "gross_trade_pnl": gross_trade_pnl,
                "net_trade_pnl": roundtrip_net_pnl,
            }
        )

    hit_rate = wins / (wins + losses) if (wins + losses) > 0 else 0.0
    turnover = total_buy_notional + total_sell_notional
    return {
        "gross_pnl": gross_pnl,
        "net_pnl": net_pnl,
        "total_costs": total_costs,
        "total_slippage": total_slippage,
        "turnover": turnover,
        "trade_count": len(trades),
        "hit_rate": hit_rate,
        "avg_trade_size": float(np.mean([t["qty"] for t in trades])) if trades else 0.0,
    }


def main() -> None:
    ticks, delivery, sectors = make_mock_data()

    fs = NseFeatureStore(FeatureStoreConfig(root=Path("./feature_store")))
    feat = fs.build_features(ticks, delivery, sectors)
    out = fs.persist_daily("2026-04-10", feat)

    feature_cols = ["ret_1", "ret_5", "vol_20", "delivery_pct", "sector_rotation_z"]

    morning = PriceFlipAlpha.morning_window(feat).reset_index(drop=True)
    split_idx = max(1000, int(len(morning) * 0.70))
    train_df = morning.iloc[:split_idx].copy()
    test_df = morning.iloc[split_idx:].copy()

    cost_engine = NSECostEngine(intraday=True)
    avg_daily_volume = float(feat["qty"].sum())
    daily_volatility = estimate_daily_volatility(feat["last_price"])
    target_col = "cost_adjusted_target"
    train_df[target_col] = build_cost_adjusted_target(
        train_df,
        cost_engine,
        horizon_ticks=20,
        representative_qty=1000,
        avg_daily_volume=avg_daily_volume,
        daily_volatility=daily_volatility,
    )
    test_df[target_col] = build_cost_adjusted_target(
        test_df,
        cost_engine,
        horizon_ticks=20,
        representative_qty=1000,
        avg_daily_volume=avg_daily_volume,
        daily_volatility=daily_volatility,
    )

    alpha = PriceFlipAlpha(AlphaModelConfig(horizon_ticks=20, target_clip=5.0))
    alpha.fit_cost_aware(train_df, feature_cols, target_col=target_col)
    report = alpha.evaluate_cost_aware(test_df, feature_cols, target_col=target_col)

    pnl_report = run_cost_aware_backtest(
        test_df,
        alpha,
        feature_cols,
        cost_engine,
        avg_daily_volume=avg_daily_volume,
        daily_volatility=daily_volatility,
        edge_threshold=0.003,
        max_trade_qty=5000,
        base_trade_qty=50,
        latency_ticks=2,
        hold_ticks=20,
        latency_half_life_ticks=2.0,
    )

    print("Bharat-Alpha Python Research")
    print(f"feature_store_file: {out}")
    print(f"train_rows: {len(train_df)}")
    print(f"test_rows: {len(test_df)}")
    print(f"avg_daily_volume: {avg_daily_volume:,.0f}")
    print(f"daily_volatility: {daily_volatility:.6f}")
    print("target: net-return label = sign(forward_ret) * max(|forward_ret| - cost_floor, 0) / daily_vol")
    print("signal_gate: edge_threshold=0.003, base_trade_qty=50, latency_ticks=2, hold_ticks=20, latency_half_life=2")
    print("cost_aware_model_report:")
    print(report)
    print("cost_aware_backtest:")
    print(f"  gross_pnl: {pnl_report['gross_pnl']:,.2f}")
    print(f"  net_pnl: {pnl_report['net_pnl']:,.2f}")
    print(f"  total_costs: {pnl_report['total_costs']:,.2f}")
    print(f"  total_slippage: {pnl_report['total_slippage']:,.2f}")
    print(f"  turnover: {pnl_report['turnover']:,.2f}")
    print(f"  trade_count: {pnl_report['trade_count']}")
    print(f"  hit_rate: {pnl_report['hit_rate']:.4f}")
    print(f"  avg_trade_size: {pnl_report['avg_trade_size']:.2f}")


if __name__ == "__main__":
    main()
