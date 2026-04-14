from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import pandas as pd


@dataclass
class FeatureStoreConfig:
    root: Path


class NseFeatureStore:
    def __init__(self, config: FeatureStoreConfig) -> None:
        self.root = config.root
        self.root.mkdir(parents=True, exist_ok=True)

    def build_features(self, ticks: pd.DataFrame, delivery: pd.DataFrame, sectors: pd.DataFrame) -> pd.DataFrame:
        df = ticks.copy()
        df["ret_1"] = df["last_price"].pct_change().fillna(0.0)
        df["ret_5"] = df["last_price"].pct_change(5).fillna(0.0)
        df["vol_20"] = df["ret_1"].rolling(20).std().fillna(0.0)

        df = df.merge(delivery[["symbol", "date", "delivery_pct"]], on=["symbol", "date"], how="left")
        df = df.merge(sectors[["symbol", "date", "sector_rotation_z"]], on=["symbol", "date"], how="left")

        df["delivery_pct"] = df["delivery_pct"].fillna(df["delivery_pct"].median())
        df["sector_rotation_z"] = df["sector_rotation_z"].fillna(0.0)
        return df

    def persist_daily(self, day: str, features: pd.DataFrame) -> Path:
        out = self.root / f"features_{day}.parquet"
        features.to_parquet(out, index=False)
        return out
