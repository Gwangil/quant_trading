"""가격 데이터 로딩: yfinance / CSV 캐시 / 번들 프록시, 레버리지 ETF 합성 및 백필."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .config import DataConfig, SyntheticConfig

TRADING_DAYS = 252


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    df.columns = [str(c).strip().title().replace(" ", "") for c in df.columns]
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df.index.name = "Date"
    if "Close" not in df.columns and "AdjClose" in df.columns:
        df["Close"] = df["AdjClose"]
    keep = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
    df = df[keep].astype(float).dropna(subset=["Close"])
    return df[~df.index.duplicated(keep="last")].sort_index()


def load_ohlc(symbol: str, source: str = "yfinance", cache_dir: str = "data/cache",
              bundled_dir: str = "data/bundled") -> pd.DataFrame:
    """단일 심볼의 일봉을 반환. 컬럼: Open High Low Close Volume (일부 없을 수 있음)."""
    if source == "bundled":
        p = Path(bundled_dir) / f"{symbol}.csv"
        if not p.exists():
            raise FileNotFoundError(f"bundled data not found: {p}")
        df = pd.read_csv(p, index_col=0)
        # 지수 데이터는 Adj Close == Close. ETF는 배당/분할 반영된 Adj Close를 쓴다.
        if "Adj Close" in df.columns:
            df["Close"] = df["Adj Close"]
        return _normalize(df)

    cache = Path(cache_dir) / f"{symbol}.csv"
    if source == "csv":
        if not cache.exists():
            raise FileNotFoundError(f"csv not found: {cache} (columns: Date, Close[, Open, High, Low, Volume])")
        return _normalize(pd.read_csv(cache, index_col=0))

    if source == "yfinance":
        try:
            import yfinance as yf  # noqa
        except ImportError as e:  # pragma: no cover
            raise ImportError("pip install yfinance 가 필요합니다 (또는 source: csv/bundled 사용)") from e
        df = yf.download(symbol, period="max", auto_adjust=True, progress=False)
        if df is None or len(df) == 0:
            if cache.exists():
                return _normalize(pd.read_csv(cache, index_col=0))
            raise RuntimeError(f"yfinance returned no data for {symbol}")
        df = _normalize(df)
        cache.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(cache)
        return df

    raise ValueError(f"unknown data source: {source}")


def synthetic_leveraged(close: pd.Series, syn: SyntheticConfig, seed_price: float = 100.0) -> pd.Series:
    """기준 지수 종가로부터 일일 리밸런싱 레버리지 ETF 가격을 합성.

    r_L = L·β·r − (expense + (L−1)·financing)/252, 가격 하한 0.
    """
    r = close.pct_change().fillna(0.0).values * syn.beta
    daily_cost = (syn.expense_ratio + max(syn.leverage - 1.0, 0.0) * syn.financing_rate) / TRADING_DAYS
    rl = syn.leverage * r - daily_cost
    rl = np.maximum(rl, -0.999)  # 하루 −100% 방지
    price = seed_price * np.cumprod(1.0 + rl)
    return pd.Series(price, index=close.index, name="Close")


def build_dataset(dc: DataConfig) -> pd.DataFrame:
    """전략 엔진이 쓰는 프레임: index=Date, columns=[close, ref_close]."""
    ref = load_ohlc(dc.reference, dc.source, dc.cache_dir, dc.bundled_dir)["Close"].rename("ref_close")

    if dc.synthetic is not None:
        close = synthetic_leveraged(ref, dc.synthetic).rename("close")
        df = pd.concat([close, ref], axis=1)
    else:
        real = load_ohlc(dc.symbol, dc.source, dc.cache_dir, dc.bundled_dir)["Close"].rename("close")
        if dc.backfill:
            syn = synthetic_leveraged(ref, SyntheticConfig())
            first = real.index[0]
            pre = syn[syn.index < first]
            if len(pre):
                # 실제 첫 가격에 이어붙이도록 스케일 조정
                scale = real.iloc[0] / syn.loc[first] if first in syn.index else real.iloc[0] / pre.iloc[-1]
                real = pd.concat([pre * scale, real])
        df = pd.concat([real.rename("close"), ref], axis=1)

    df = df.dropna(subset=["close"])
    df["ref_close"] = df["ref_close"].ffill()
    df = df.dropna()
    if dc.end:
        df = df[df.index <= pd.Timestamp(dc.end)]
    return df
