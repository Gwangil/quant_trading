"""성과 지표: 단리/복리 수익률, MDD, 회복기간, 연도별 수익률 등."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .data import TRADING_DAYS


def drawdown_episodes(equity: pd.Series, min_depth: float = 0.10) -> pd.DataFrame:
    """고점→저점→회복 에피소드. recovered=False 면 기간 말까지 미회복."""
    peak = equity.cummax()
    dd = equity / peak - 1.0
    eps = []
    in_dd = False
    start = trough = None
    for date, v in dd.items():
        if not in_dd and v < 0:
            in_dd, start, trough = True, date, date
        elif in_dd:
            if v < dd.loc[trough]:
                trough = date
            if v >= 0:
                eps.append((start, trough, date, dd.loc[trough], True))
                in_dd = False
    if in_dd:
        eps.append((start, trough, dd.index[-1], dd.loc[trough], False))
    out = pd.DataFrame(eps, columns=["peak", "trough", "recovery", "depth", "recovered"])
    if len(out) == 0:
        return out
    out["days_to_trough"] = (out["trough"] - out["peak"]).dt.days
    out["days_to_recover"] = (out["recovery"] - out["trough"]).dt.days
    out["total_days"] = (out["recovery"] - out["peak"]).dt.days
    return out[out["depth"] <= -min_depth].reset_index(drop=True)


def compute_metrics(equity: pd.Series, exposure: pd.Series | None = None,
                    baskets: pd.DataFrame | None = None, trades: pd.DataFrame | None = None) -> dict:
    eq = equity.dropna()
    if len(eq) < 2:
        return {}
    years = (eq.index[-1] - eq.index[0]).days / 365.25
    total = eq.iloc[-1] / eq.iloc[0] - 1.0
    r = eq.pct_change().dropna()
    dd = eq / eq.cummax() - 1.0
    mdd = float(dd.min())
    trough = dd.idxmin()
    peak = eq.loc[:trough].idxmax()
    after = eq.loc[trough:]
    rec = after[after >= eq.loc[peak]]
    recovery_date = rec.index[0] if len(rec) else None
    ann_vol = float(r.std() * np.sqrt(TRADING_DAYS))
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / years) - 1 if years > 0 else np.nan
    downside = r[r < 0].std() * np.sqrt(TRADING_DAYS)
    yearly = eq.resample("YE").last().pct_change()
    first_year = eq.resample("YE").last().iloc[0] / eq.iloc[0] - 1
    yearly.iloc[0] = first_year
    eps = drawdown_episodes(eq, 0.10)
    underwater = (eq.index.to_series().diff().dt.days.fillna(0) * (dd < 0)).groupby((dd >= 0).cumsum()).sum()
    m = {
        "start": eq.index[0].date().isoformat(),
        "end": eq.index[-1].date().isoformat(),
        "years": round(years, 2),
        "total_return": total,
        "simple_annual": total / years if years > 0 else np.nan,   # 단리 연환산
        "cagr": cagr,
        "ann_vol": ann_vol,
        "sharpe": float(r.mean() / r.std() * np.sqrt(TRADING_DAYS)) if r.std() > 0 else np.nan,
        "sortino": float(r.mean() * TRADING_DAYS / downside) if downside and downside > 0 else np.nan,
        "mdd": mdd,
        "mdd_peak": peak.date().isoformat(),
        "mdd_trough": trough.date().isoformat(),
        "mdd_recovery": recovery_date.date().isoformat() if recovery_date is not None else None,
        "mdd_recover_days": int((recovery_date - trough).days) if recovery_date is not None else None,
        "max_underwater_days": int(underwater.max()) if len(underwater) else 0,
        "calmar": (cagr / abs(mdd)) if mdd < 0 else np.nan,
        "worst_year": float(yearly.min()),
        "best_year": float(yearly.max()),
        "pct_positive_years": float((yearly > 0).mean()),
        "n_dd_episodes_10pct": int(len(eps)),
        "avg_recover_days_10pct": float(eps.loc[eps["recovered"], "days_to_recover"].mean()) if len(eps) and eps["recovered"].any() else np.nan,
        "yearly_returns": {str(k.year): float(v) for k, v in yearly.items()},
    }
    monthly = eq.resample("ME").last().pct_change().dropna()
    m["ulcer_index"] = float(np.sqrt((dd ** 2).mean()))          # 낙폭 제곱평균의 제곱근 (낙폭 깊이×기간)
    m["worst_month"] = float(monthly.min()) if len(monthly) else np.nan
    m["pct_months_positive"] = float((monthly > 0).mean()) if len(monthly) else np.nan
    m["pct_days_dd_gt10"] = float((dd <= -0.10).mean())
    m["pct_days_dd_gt20"] = float((dd <= -0.20).mean())
    neg = (monthly < 0).astype(int)
    m["max_losing_months_streak"] = int((neg.groupby((neg == 0).cumsum()).cumsum()).max()) if len(monthly) else 0
    if exposure is not None:
        m["avg_exposure"] = float(exposure.mean())
    if baskets is not None and len(baskets):
        closed = baskets[baskets["status"] == "closed"]
        m["n_baskets_closed"] = int(len(closed))
        m["basket_win_rate"] = float((closed["ret"] > 0).mean()) if len(closed) else np.nan
        m["basket_avg_ret"] = float(closed["ret"].mean()) if len(closed) else np.nan
        m["basket_avg_hold_days"] = float(closed["hold_days"].mean()) if len(closed) else np.nan
        m["basket_exit_reasons"] = closed["reason"].value_counts().to_dict() if len(closed) else {}
    if trades is not None:
        m["n_trades"] = int(len(trades))
    return m


def buy_and_hold(close: pd.Series, initial: float) -> pd.Series:
    return (close / close.iloc[0] * initial).rename("bh")


def fmt_pct(x) -> str:
    return "-" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x * 100:.1f}%"
