"""기준 전략(baseline / v5) 과 본 프로젝트 프로필을 같은 데이터·비용·지표로 비교."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .config import StrategyConfig
from .data import build_dataset
from .engine import run_backtest
from .metrics import compute_metrics, buy_and_hold, fmt_pct
from .profiles import build, PROFILES
from .reference import run_reference, BASELINE, V5, ReferenceParams
import dataclasses

PERIODS = {"full": (None, None), "IS ~2017": (None, "2017-12-31"), "OOS 2018~": ("2018-01-01", None)}


def cap_metrics(eq: pd.Series, capital: float) -> dict:
    """invest_strategy 방식: 달러 손익 ÷ 초기자본 (단리), MDD 도 자본 대비."""
    yrs = (eq.index[-1] - eq.index[0]).days / 365.25
    dd = (eq - eq.cummax()) / capital
    return {"pnl_yr_cap": (eq.iloc[-1] - eq.iloc[0]) / capital / yrs, "mdd_cap": float(dd.min())}


def _slice(eq: pd.Series, period: str) -> pd.Series:
    s, e = PERIODS[period]
    out = eq
    if s: out = out[out.index >= pd.Timestamp(s)]
    if e: out = out[out.index <= pd.Timestamp(e)]
    return out


def collect(capital: float = 100_000_000.0, data_key: str = "hybrid", profiles: list[str] | None = None,
            modes: tuple[str, ...] = ("equity", "fixed")) -> tuple[pd.DataFrame, dict[str, pd.Series]]:
    """행: (전략, 기간) × 지표. 반환: (표, 전략별 equity)."""
    base_cfg = build("balanced", data_key)
    base_cfg.initial_capital = capital
    df = build_dataset(base_cfg.data)
    rsi = None
    try:
        raw = pd.read_csv(Path(base_cfg.data.bundled_dir) / f"{base_cfg.data.symbol}.csv", index_col=0, parse_dates=True)
        rsi = raw["RSI"] if "RSI" in raw else None
    except FileNotFoundError:
        pass
    curves: dict[str, pd.Series] = {}
    trades: dict[str, int] = {}
    exposures: dict[str, pd.Series] = {}
    refs = [("baseline", BASELINE), ("v5", V5), ("v5(compound)", dataclasses.replace(V5, compound=True))]
    for name, params in refs:
        eq, n, fills = run_reference(df["close"], capital, params, rsi=rsi)
        curves[name] = eq; trades[name] = fills
    for prof in (profiles or list(PROFILES)):
        for mode in modes:
            cfg = build(prof, data_key); cfg.initial_capital = capital
            cfg.baskets.budget_mode = mode
            res = run_backtest(cfg, df)
            key = f"{prof}" + ("" if mode == "equity" else "(fixed)")
            curves[key] = res.equity; trades[key] = int(len(res.trades)); exposures[key] = res.frame["exposure"]
    curves["SOXL 보유"] = buy_and_hold(df["close"].reindex(curves["baseline"].index).dropna(), capital)

    rows = []
    for name, eq in curves.items():
        for period in PERIODS:
            seg = _slice(eq, period)
            if len(seg) < 30:
                continue
            m = compute_metrics(seg, exposures[name].reindex(seg.index) if name in exposures else None)
            c = cap_metrics(seg, capital)
            rows.append({"strategy": name, "period": period, "cagr": m["cagr"], "simple_annual": m["simple_annual"],
                         "pnl_yr_cap": c["pnl_yr_cap"], "mdd": m["mdd"], "mdd_cap": c["mdd_cap"],
                         "mdd_recover_days": m["mdd_recover_days"], "max_underwater_days": m["max_underwater_days"],
                         "worst_year": m["worst_year"], "worst_month": m["worst_month"], "ulcer": m["ulcer_index"],
                         "pct_days_dd_gt20": m["pct_days_dd_gt20"], "sharpe": m["sharpe"], "calmar": m["calmar"],
                         "pct_positive_years": m["pct_positive_years"], "avg_exposure": m.get("avg_exposure", np.nan),
                         "n_trades": trades.get(name, np.nan),
                         "fills_per_day": (trades[name] / len(curves[name])) if name in trades else np.nan})
    return pd.DataFrame(rows), curves


def render(table: pd.DataFrame, period: str) -> str:
    t = table[table.period == period]
    cols = [("strategy", "전략"), ("cagr", "CAGR"), ("pnl_yr_cap", "자본대비 단리/yr"), ("mdd", "MDD"), ("mdd_cap", "MDD/자본"),
            ("mdd_recover_days", "MDD 회복일"), ("max_underwater_days", "최장 수중일"), ("worst_year", "최악 연도"),
            ("worst_month", "최악의 달"), ("ulcer", "Ulcer"), ("pct_days_dd_gt20", "낙폭>20% 체류"), ("sharpe", "Sharpe"),
            ("calmar", "Calmar"), ("avg_exposure", "투자비중"), ("fills_per_day", "체결/일")]
    lines = ["| " + " | ".join(c[1] for c in cols) + " |", "|" + "---|" * len(cols)]
    for _, r in t.iterrows():
        vals = []
        for k, _ in cols:
            v = r[k]
            if k == "strategy": vals.append(str(v))
            elif k in ("mdd_recover_days", "max_underwater_days", "n_trades"): vals.append("-" if pd.isna(v) else f"{int(v)}")
            elif k in ("ulcer", "sharpe", "calmar", "fills_per_day"): vals.append("-" if pd.isna(v) else f"{v:.2f}")
            else: vals.append(fmt_pct(v))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def write(out_dir: str | Path = "reports", capital: float = 100_000_000.0) -> pd.DataFrame:
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    table, curves = collect(capital)
    table.to_csv(out / "compare_reference.csv", index=False)
    pd.DataFrame(curves).to_csv(out / "compare_reference_equity.csv")
    md = ["# 기준 전략(baseline / v5) vs 프로필 비교", "",
          f"실제 SOXL 하이브리드 2001-08~2026-07, 자본 {capital:,.0f}, 수수료 0.1%/편도, 종가 체결. "
          "`(fixed)` = 바스켓 예산을 초기자본/4 로 고정한 단리 모드(기준 전략과 같은 구조). "
          "`v5(compound)` = v5 의 바구니 예산을 현재 총자산/8 로 갱신한 복리 변형(본 프로젝트 기본 모드와 같은 구조).", ""]
    for period in PERIODS:
        md += [f"## {period}", "", render(table, period), ""]
    (out / "compare_reference.md").write_text("\n".join(md), encoding="utf-8")
    return table
