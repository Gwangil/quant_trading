"""세후 원화 지표: 달러 성과를 원화로 환산하고 한국 세제(해외주식 양도소득세·배당소득세)를 반영한다.

가정 (2026 현행 기준, 세율·공제는 인자로 조정 가능)
- 양도소득세: 연간 실현손익(매도가 − 매입가 − 수수료, **각 거래일 환율로 원화 환산**) 합계에서
  기본공제 250만원을 뺀 금액의 22%(지방세 포함). 손실은 같은 해 이익과 상계, 이월 없음.
  세액은 실현되는 즉시 **미지급 부채로 일할 계상**(그해 누적 실현손익 기준)하고, 다음 해 5월 31일 납부 시 계좌에서
  인출(비율 차감 → 이후 복리 감소 반영). 따라서 연말·납부일에 인위적 급락이 생기지 않고 낙폭에는 부채가 자연히 반영된다.
- 배당소득세: 현금 파킹 이자에 15.4% 원천징수 (발생일 차감).
- 환전: 시작 시 원→달러, 종료 시 달러→원 각 1회, 스프레드 `fx_spread_pct`.
- 환율: data/cache/USDKRW.csv(일별, `qtrade data update USDKRW`) 가 있으면 사용, 없으면
  data/bundled/USDKRW_annual.csv(연평균 근사) 를 연중앙 기준 선형보간.
결과: 세전 USD / 세전 KRW / 세후 KRW 자산곡선과 지표, 연도별 표(달러 수익률, 환율 변동, 원화 수익률, 세금, 세후 수익률).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .engine import BacktestResult
from .metrics import compute_metrics, fmt_pct


@dataclass
class TaxParams:
    capital_gains_rate: float = 0.22       # 양도세 20% + 지방소득세 2%
    basic_deduction_krw: float = 2_500_000
    dividend_rate: float = 0.154           # 이자·배당 원천징수
    fx_spread_pct: float = 0.001           # 환전 편도 스프레드
    pay_month: int = 5                     # 납부월 (다음 해)
    pay_day: int = 31


def load_fx(index: pd.DatetimeIndex, cache_dir="data/cache", bundled_dir="data/bundled") -> tuple[pd.Series, str]:
    """index 에 맞춘 원/달러 시리즈와 출처 문자열."""
    p = Path(cache_dir) / "USDKRW.csv"
    if p.exists():
        fx = pd.read_csv(p, index_col=0, parse_dates=True)["Close"].astype(float)
        fx = fx.reindex(index.union(fx.index)).ffill().reindex(index).bfill()
        return fx, f"daily ({p})"
    tbl = pd.read_csv(Path(bundled_dir) / "USDKRW_annual.csv").set_index("year")["rate"]
    mids = pd.Series(tbl.values, index=pd.to_datetime([f"{y}-07-01" for y in tbl.index]))
    fx = mids.reindex(mids.index.union(index)).interpolate(method="time").reindex(index).ffill().bfill()
    return fx, "annual-average approximation (data/bundled/USDKRW_annual.csv)"


def realized_gains_krw(trades: pd.DataFrame, fx: pd.Series) -> pd.DataFrame:
    """매도 건별 원화 실현손익. 매입 원가는 각 로트 매입일 환율, 매도는 매도일 환율. 수수료는 양쪽 차감."""
    sells = trades[(trades.side == "SELL") & trades["lots"].notna()] if "lots" in trades else trades.iloc[0:0]
    buy_fee_rate = None
    if len(trades):
        buys = trades[trades.side == "BUY"]
        buy_fee_rate = float((buys.fee / buys.value).mean()) if len(buys) and (buys.value > 0).any() else 0.0
    rows = []
    for _, t in sells.iterrows():
        fx_s = float(fx.loc[t.date])
        proceeds_krw = (t.value - t.fee) * fx_s
        basis_krw = 0.0
        for q, c, d in t.lots:
            basis_krw += q * c * (1 + (buy_fee_rate or 0.0)) * float(fx.loc[pd.Timestamp(d)])
        rows.append({"date": t.date, "year": t.date.year, "gain_krw": proceeds_krw - basis_krw, "gain_usd": t.pnl})
    return pd.DataFrame(rows, columns=["date", "year", "gain_krw", "gain_usd"])


def after_tax(res: BacktestResult, params: TaxParams = TaxParams(), fx: pd.Series | None = None,
              cache_dir="data/cache", bundled_dir="data/bundled") -> dict:
    eq = res.equity
    idx = eq.index
    if fx is None:
        fx, fx_src = load_fx(idx, cache_dir, bundled_dir)
    else:
        fx_src = "given"
    fx = fx.reindex(idx).ffill().bfill()
    # 세전 원화: 시작 환전 스프레드 반영 (초기자본 KRW → USD 를 사 들어감), 종료 시 스프레드는 지표 산출용 마지막 값에 반영
    krw_pre = eq * fx
    krw_pre.iloc[-1] = krw_pre.iloc[-1] * (1 - params.fx_spread_pct)
    krw_pre = krw_pre / (1 + params.fx_spread_pct)   # 시작 환전 비용: 같은 USD 를 사려면 KRW 가 더 들었음 → 수익률 기준 하향

    # --- 이자 원천징수 (일별 비율 차감) ---
    interest = res.frame["interest"].reindex(idx).fillna(0.0) if "interest" in res.frame else pd.Series(0.0, index=idx)
    div_tax_usd = interest * params.dividend_rate
    haircut = (1 - (div_tax_usd / eq).clip(lower=0, upper=0.5)).cumprod()

    # --- 양도세: 일할 부채 계상 + 다음 해 납부일 인출 ---
    gains = realized_gains_krw(res.trades, fx)
    yearly_gain = gains.groupby("year")["gain_krw"].sum() if len(gains) else pd.Series(dtype=float)
    tax_by_year = ((yearly_gain - params.basic_deduction_krw).clip(lower=0) * params.capital_gains_rate)
    daily_gain = gains.groupby("date")["gain_krw"].sum().reindex(idx).fillna(0.0) if len(gains) else pd.Series(0.0, index=idx)
    ytd = daily_gain.groupby(idx.year).cumsum()
    liability = ((ytd - params.basic_deduction_krw).clip(lower=0) * params.capital_gains_rate)   # 당해연도 미지급
    tax_events = []   # (납부일, 세액 KRW)
    years = pd.Index(idx.year)
    for y, tax in tax_by_year.items():
        if tax <= 0:
            continue
        pay = pd.Timestamp(year=int(y) + 1, month=params.pay_month, day=params.pay_day)
        if pay > idx[-1]:
            continue             # 기간 말까지 미납 → 부채로만 남김
        pay = idx[idx.searchsorted(pay)]
        tax_events.append((pay, float(tax)))
        # 1/1 ~ 납부일 전날: 전년도 확정 세액을 부채로 유지
        mask = (years == int(y) + 1) & (idx < pay)
        liability.loc[mask] += float(tax)
    # 기간 말 미납 연도(마지막 해 + 납부일 전 전년도)는 liability 에 이미 포함
    krw_after = (krw_pre * haircut).copy()
    factor = pd.Series(1.0, index=idx)
    for pay, tax in tax_events:
        base = float(krw_after.loc[pay] * factor.loc[pay])
        if base <= 0:
            continue
        factor.loc[pay:] *= max(0.0, 1 - tax / base)
    krw_after = krw_after * factor - liability
    unpaid = float(liability.iloc[-1])

    # --- 연도별 표 ---
    ye = pd.DataFrame({"usd": eq, "fx": fx, "krw_pre": krw_pre, "krw_after": krw_after}).resample("YE").last()
    first = pd.DataFrame({"usd": [eq.iloc[0]], "fx": [fx.iloc[0]], "krw_pre": [krw_pre.iloc[0]], "krw_after": [krw_after.iloc[0]]})
    prev = pd.concat([first, ye.iloc[:-1].reset_index(drop=True)], ignore_index=True)
    rows = []
    taxes_paid = pd.Series({p: t for p, t in tax_events}).groupby(lambda d: d.year).sum() if tax_events else pd.Series(dtype=float)
    for i, (d, r) in enumerate(ye.iterrows()):
        y = d.year
        rows.append({"year": y, "usd_ret": r.usd / prev.usd[i] - 1, "fx_end": r.fx, "fx_chg": r.fx / prev.fx[i] - 1,
                     "krw_ret": r.krw_pre / prev.krw_pre[i] - 1,
                     "realized_gain_krw": float(yearly_gain.get(y, 0.0)), "tax_assessed_krw": float(tax_by_year.get(y, 0.0)),
                     "tax_paid_krw": float(taxes_paid.get(y, 0.0)), "krw_after_ret": r.krw_after / prev.krw_after[i] - 1})
    yearly = pd.DataFrame(rows)

    m_usd, m_krw, m_after = compute_metrics(eq), compute_metrics(krw_pre), compute_metrics(krw_after)
    total_tax = float(sum(t for _, t in tax_events)) + unpaid; total_div_tax_krw = float((div_tax_usd * fx).sum())
    return {"fx_source": fx_src, "fx": fx, "usd": eq, "krw_pre": krw_pre, "krw_after": krw_after, "yearly": yearly,
            "metrics": {"USD 세전": m_usd, "KRW 세전": m_krw, "KRW 세후": m_after},
            "total_capital_gains_tax_krw": total_tax, "unpaid_tax_krw": unpaid, "total_dividend_tax_krw": total_div_tax_krw,
            "tax_drag_cagr": m_krw["cagr"] - m_after["cagr"], "params": params}


def render(out: dict, title: str) -> str:
    m = out["metrics"]; p = out["params"]
    keys = [("cagr", "CAGR"), ("simple_annual", "단리 연수익"), ("mdd", "MDD"), ("mdd_recover_days", "MDD 회복일"),
            ("worst_year", "최악 연도"), ("worst_month", "최악의 달"), ("sharpe", "Sharpe"), ("total_return", "총수익")]
    lines = [f"# {title} — 달러 / 원화 / 세후 원화", "",
             f"- 환율: {out['fx_source']}", f"- 양도세 {p.capital_gains_rate:.0%} (기본공제 {p.basic_deduction_krw:,.0f}원, 다음 해 {p.pay_month}월 납부), "
             f"이자 원천징수 {p.dividend_rate:.1%}, 환전 스프레드 편도 {p.fx_spread_pct:.2%}",
             f"- 누적 양도세 {out['total_capital_gains_tax_krw']:,.0f}원 (기간 말 미납 부채 {out['unpaid_tax_krw']:,.0f}원 포함), 누적 이자세 {out['total_dividend_tax_krw']:,.0f}원, 세금으로 인한 CAGR 손실 {out['tax_drag_cagr']:.2%}p", "",
             "| 지표 | " + " | ".join(m.keys()) + " |", "|---|" + "---|" * len(m)]
    for k, label in keys:
        vals = []
        for mm in m.values():
            v = mm.get(k)
            vals.append(f"{v:.2f}" if k == "sharpe" else (("미회복" if v is None else str(v)) if k == "mdd_recover_days" else fmt_pct(v)))
        lines.append(f"| {label} | " + " | ".join(vals) + " |")
    y = out["yearly"]
    lines += ["", "## 연도별", "", "| 연도 | 달러 수익률 | 환율(연말) | 환율 변동 | 원화 수익률(세전) | 실현손익(원) | 양도세 산출(원) | 납부(원) | 원화 수익률(세후) |", "|---|---|---|---|---|---|---|---|---|"]
    for _, r in y.iterrows():
        lines.append(f"| {int(r.year)} | {fmt_pct(r.usd_ret)} | {r.fx_end:,.0f} | {fmt_pct(r.fx_chg)} | {fmt_pct(r.krw_ret)} | {r.realized_gain_krw:,.0f} | {r.tax_assessed_krw:,.0f} | {r.tax_paid_krw:,.0f} | {fmt_pct(r.krw_after_ret)} |")
    return "\n".join(lines)


def write(res: BacktestResult, out_dir: str | Path, name: str, params: TaxParams = TaxParams(), **kw) -> dict:
    out = after_tax(res, params, **kw)
    d = Path(out_dir); d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}_tax.md").write_text(render(out, name), encoding="utf-8")
    out["yearly"].to_csv(d / f"{name}_tax_yearly.csv", index=False)
    pd.DataFrame({"usd": out["usd"], "fx": out["fx"], "krw_pre": out["krw_pre"], "krw_after": out["krw_after"]}).to_csv(d / f"{name}_tax_equity.csv")
    return out
