"""전략에 필요한 최소한의 지표."""
from __future__ import annotations

import numpy as np
import pandas as pd


def realized_vol(close: pd.Series, window: int) -> pd.Series:
    """로그수익률 표준편차(일 단위). 창이 안 차면 NaN."""
    lr = np.log(close).diff()
    return lr.rolling(window, min_periods=window).std()


def sma(close: pd.Series, window: int) -> pd.Series:
    return close.rolling(window, min_periods=window).mean()


def drawdown(equity: pd.Series) -> pd.Series:
    peak = equity.cummax()
    return equity / peak - 1.0
