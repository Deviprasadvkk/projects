from __future__ import annotations

from dataclasses import dataclass
from typing import List
import numpy as np
import pandas as pd

try:
    from xgboost import XGBRegressor
except Exception:  # pragma: no cover
    XGBRegressor = None

from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score


@dataclass
class AlphaModelConfig:
    horizon_ticks: int = 20
    target_clip: float = 5.0


class PriceFlipAlpha:
    def __init__(self, config: AlphaModelConfig) -> None:
        self.config = config
        self.model = None

    def make_regression_target(self, df: pd.DataFrame, target_col: str) -> pd.Series:
        y = df[target_col].replace([np.inf, -np.inf], np.nan).fillna(0.0)
        return y.clip(-self.config.target_clip, self.config.target_clip)

    @staticmethod
    def morning_window(df: pd.DataFrame) -> pd.DataFrame:
        ts = pd.to_datetime(df["ts"])
        mask = (ts.dt.time >= pd.to_datetime("09:15:00").time()) & (ts.dt.time <= pd.to_datetime("10:00:00").time())
        return df.loc[mask].copy()

    def fit(self, df: pd.DataFrame, feature_cols: List[str]) -> None:
        raise NotImplementedError("Use fit_cost_aware for regression training")

    def fit_cost_aware(self, df: pd.DataFrame, feature_cols: List[str], target_col: str) -> None:
        df = self.morning_window(df)
        y = self.make_regression_target(df, target_col)
        x = df[feature_cols].fillna(0.0)

        if XGBRegressor is not None:
            self.model = XGBRegressor(
                n_estimators=350,
                max_depth=6,
                learning_rate=0.05,
                subsample=0.9,
                colsample_bytree=0.9,
                random_state=42,
                reg_alpha=0.1,
                reg_lambda=1.0,
                objective="reg:squarederror",
            )
        else:
            self.model = HistGradientBoostingRegressor(max_depth=6, learning_rate=0.05, random_state=42)

        self.model.fit(x, y)

    def evaluate_cost_aware(self, df: pd.DataFrame, feature_cols: List[str], target_col: str) -> str:
        df = self.morning_window(df)
        y = self.make_regression_target(df, target_col)
        x = df[feature_cols].fillna(0.0)
        pred = pd.Series(self.model.predict(x), index=df.index)

        mae = mean_absolute_error(y, pred)
        r2 = r2_score(y, pred)
        realized_dir = np.sign(y)
        pred_dir = np.sign(pred)
        dir_acc = float((realized_dir == pred_dir).mean())
        return f"mae={mae:.6f}, r2={r2:.6f}, directional_acc={dir_acc:.4f}"

    def predict_edge(self, rows: pd.DataFrame, feature_cols: List[str]) -> pd.Series:
        x = rows[feature_cols].fillna(0.0)
        return pd.Series(self.model.predict(x), index=rows.index)
