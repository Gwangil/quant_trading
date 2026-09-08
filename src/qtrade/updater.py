"""시세 갱신: yfinance 최신 일봉 + 번들 스냅샷 이어붙이기 → data/cache/{SYMBOL}.csv

- yfinance 는 수정주가(auto_adjust) 기준. 번들 스냅샷(2001~)은 yfinance 첫 날짜 이전 구간만 쓰고,
  이어붙이는 날의 가격 비율로 스케일해 불연속을 없앤다.
- 저장 전 필터(auto_trade updater 참고): 미완성 당일 봉(미 동부 16:10 이전) · OHLC 불변식 위반 봉 제외.
"""
from __future__ import annotations

import logging
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from .data import _normalize

logger = logging.getLogger(__name__)
US_EASTERN = ZoneInfo("America/New_York")
SESSION_CLOSE_BUFFER = dtime(16, 10)


def last_complete_session(now_et: datetime | None = None) -> pd.Timestamp:
    now_et = now_et or datetime.now(US_EASTERN)
    cutoff = pd.Timestamp(now_et.date())
    if now_et.time() < SESSION_CLOSE_BUFFER:
        cutoff -= pd.Timedelta(days=1)
    return cutoff


def sanitize_daily(df: pd.DataFrame, symbol: str = "", now_et: datetime | None = None) -> pd.DataFrame:
    """미완성 당일 봉 + OHLC 위반 봉 제거."""
    if df.empty:
        return df
    cutoff = last_complete_session(now_et)
    fut = df.index > cutoff
    if fut.any():
        logger.warning("%s: 미완성 세션 봉 %d행 제외", symbol, int(fut.sum()))
        df = df.loc[~fut]
    if {"Open", "High", "Low"}.issubset(df.columns):
        bad = (df["High"] < df[["Open", "Close"]].max(axis=1)) | (df["Low"] > df[["Open", "Close"]].min(axis=1))
        if bad.any():
            logger.warning("%s: OHLC 불변식 위반 %d행 제외", symbol, int(bad.sum()))
            df = df.loc[~bad]
    return df


def splice(bundled: pd.DataFrame | None, fresh: pd.DataFrame) -> pd.DataFrame:
    """번들(과거) + 최신(yfinance). 겹치는 첫 날의 종가 비율로 번들 구간을 스케일."""
    if bundled is None or bundled.empty:
        return fresh
    first = fresh.index[0]
    pre = bundled[bundled.index < first]
    if pre.empty:
        return fresh
    if first in bundled.index:
        scale = float(fresh["Close"].iloc[0] / bundled.loc[first, "Close"])
    else:
        scale = float(fresh["Close"].iloc[0] / pre["Close"].iloc[-1])
    pre = pre.copy()
    for c in ("Open", "High", "Low", "Close"):
        if c in pre.columns:
            pre[c] = pre[c] * scale
    out = pd.concat([pre, fresh])
    return out[~out.index.duplicated(keep="last")].sort_index()


def fetch_yf(symbol: str) -> pd.DataFrame:
    import yfinance as yf
    df = yf.download(symbol, period="max", auto_adjust=True, progress=False)
    if df is None or len(df) == 0:
        raise RuntimeError(f"yfinance returned no data for {symbol}")
    return _normalize(df)


def update_symbol(symbol: str, cache_dir: str = "data/cache", bundled_dir: str = "data/bundled",
                  fetch=fetch_yf) -> dict:
    fresh = sanitize_daily(fetch(symbol), symbol)
    bpath = Path(bundled_dir) / f"{symbol}.csv"
    bundled = None
    if bpath.exists():
        b = pd.read_csv(bpath, index_col=0, parse_dates=True)
        b.index.name = "Date"
        if "Adj Close" in b.columns:
            b["Close"] = b["Adj Close"]
        bundled = b[[c for c in ("Open", "High", "Low", "Close", "Volume") if c in b.columns]]
    merged = splice(bundled, fresh)
    out = Path(cache_dir) / f"{symbol}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(out, float_format="%.6f")
    return {"symbol": symbol, "rows": len(merged), "first": merged.index[0].date().isoformat(),
            "last": merged.index[-1].date().isoformat(), "fresh_from": fresh.index[0].date().isoformat(), "path": str(out)}


def staleness_days(last: pd.Timestamp, now_et: datetime | None = None) -> int:
    return int((last_complete_session(now_et) - pd.Timestamp(last)).days)
