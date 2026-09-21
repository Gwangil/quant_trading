"""다전략 포트폴리오: 슬리브(전략 설정 + 자본 비중)를 각각 돌려 결합한다.

- 각 슬리브는 자기 자본(총자본 × weight)으로 독립 운용. 슬리브 간 리밸런싱은 `rebalance: none|yearly|risk_parity`.
  risk_parity: 매년 첫 거래일에 직전 `rp_lookback`(기본 252) 거래일 슬리브 수익률 변동성의 역수에 비례해 비중 결정
  (weight 는 상한 `rp_max_weight` 및 초기값으로만 쓰임). 미래참조 없음(직전 연도 변동성).
- 결합 자산곡선·지표·슬리브 간 상관·개별 vs 결합 비교, 그리고 **통합 주문서**(슬리브 주문을 종목·방향·유형·가격으로 합산)를 낸다.
YAML:
  name: multi_soxl
  initial_capital: 100000
  rebalance: yearly
  sleeves:
    - {config: configs/soxl_balanced.yaml, weight: 0.6}
    - {config: configs/trend_soxl.yaml, weight: 0.4}
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from .metrics import compute_metrics, fmt_pct
from .strategies import load_any, run_any


def load_portfolio(path):
    raw = yaml.safe_load(open(path, encoding="utf-8"))
    raw.setdefault("rebalance", "none"); raw.setdefault("initial_capital", 100_000.0)
    return raw


def run_portfolio(spec: dict) -> dict:
    cap = float(spec["initial_capital"])
    results, names, weights = [], [], []
    for s in spec["sleeves"]:
        cfg, kind = load_any(s["config"])
        cfg.initial_capital = cap * float(s["weight"])
        res = run_any(cfg, kind)
        results.append(res); names.append(s.get("name") or cfg.name); weights.append(float(s["weight"]))
    idx = results[0].equity.index
    for r in results[1:]:
        idx = idx.intersection(r.equity.index)
    eqs = pd.DataFrame({n: r.equity.reindex(idx) for n, r in zip(names, results)})
    rets = eqs.pct_change().fillna(0.0)
    weight_log = []
    if spec["rebalance"] in ("yearly", "risk_parity"):
        # 매년 첫 거래일에 목표 비중으로 리밸런싱 (슬리브 수익률 결합)
        w0 = np.array(weights) / sum(weights)
        lookback = int(spec.get("rp_lookback", 252)); wmax = float(spec.get("rp_max_weight", 1.0))
        def target(t):
            if spec["rebalance"] != "risk_parity" or t < lookback:
                return w0
            vol = rets.iloc[t - lookback:t].std().values
            inv = np.where(vol > 0, 1.0 / vol, 0.0)
            w = inv / inv.sum() if inv.sum() > 0 else w0
            w = np.minimum(w, wmax); return w / w.sum()
        combined = [cap]; cur_w = w0.copy(); val = cap; year = idx[0].year
        weight_log.append((idx[0], cur_w.copy()))
        for t in range(1, len(idx)):
            if idx[t].year != year:
                cur_w = target(t); year = idx[t].year; weight_log.append((idx[t], cur_w.copy()))
            growth = 1 + rets.iloc[t].values
            sleeve_vals = cur_w * val * growth
            val = float(sleeve_vals.sum()); cur_w = sleeve_vals / val
            combined.append(val)
        comb = pd.Series(combined, index=idx, name="portfolio")
    else:
        comb = eqs.sum(axis=1).rename("portfolio")
    corr = rets.corr()
    metrics = {n: compute_metrics(eqs[n]) for n in names}
    metrics["portfolio"] = compute_metrics(comb)
    wl = pd.DataFrame([dict(date=d, **{n: w for n, w in zip(names, ws)}) for d, ws in weight_log]).set_index("date") if weight_log else pd.DataFrame()
    return {"names": names, "weights": weights, "results": results, "equities": eqs, "portfolio": comb,
            "metrics": metrics, "corr": corr, "spec": spec, "weight_log": wl}


def combined_orders(out: dict) -> pd.DataFrame:
    """슬리브 주문을 (symbol, side, kind, limit) 로 합산. limit None(MOC) 은 함께 묶임."""
    rows = []
    for n, r in zip(out["names"], out["results"]):
        sym = r.cfg.data.symbol
        for o in r.pending_orders:
            rows.append({"sleeve": n, "symbol": sym, "side": o.side, "kind": o.kind,
                         "limit": None if o.limit is None else round(float(o.limit), 2), "qty": o.qty, "reason": o.reason})
    if not rows:
        return pd.DataFrame(columns=["symbol", "side", "kind", "limit", "qty", "sleeves"])
    df = pd.DataFrame(rows)
    g = df.groupby(["symbol", "side", "kind", "limit"], dropna=False).agg(qty=("qty", "sum"), sleeves=("sleeve", lambda s: "+".join(sorted(set(s))))).reset_index()
    g["qty"] = g["qty"].astype(int)
    return g[g.qty > 0].sort_values(["symbol", "side", "limit"], na_position="first")


def _md(df: pd.DataFrame, fmt=lambda v: v) -> str:
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join([""] + cols) + " |", "|---|" + "---|" * len(cols)]
    for i, r in df.iterrows():
        lines.append("| " + " | ".join([str(i)] + [("" if pd.isna(v) else str(fmt(v))) for v in r.values]) + " |")
    return "\n".join(lines)


def render(out: dict, title: str) -> str:
    m = out["metrics"]
    cols = list(m.keys())
    lines = [f"# {title}", "", f"- 슬리브: " + ", ".join(f"{n} {w:.0%}" for n, w in zip(out['names'], out['weights'])) + f", 리밸런싱: {out['spec']['rebalance']}", "",
             "| 지표 | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols)]
    for k, label in [("cagr", "CAGR"), ("mdd", "MDD"), ("mdd_recover_days", "MDD 회복일"), ("max_underwater_days", "최장 수중일"), ("worst_year", "최악 연도"),
                     ("worst_month", "최악의 달"), ("sharpe", "Sharpe"), ("calmar", "Calmar"), ("ulcer_index", "Ulcer"), ("avg_exposure", "투자비중")]:
        vals = []
        for c in cols:
            v = m[c].get(k)
            vals.append(f"{v:.2f}" if k in ("sharpe", "calmar", "ulcer_index") else (("-" if v is None else str(v)) if k in ("mdd_recover_days", "max_underwater_days") else fmt_pct(v)))
        lines.append(f"| {label} | " + " | ".join(vals) + " |")
    lines += ["", "## 슬리브 일간수익률 상관", "", _md(out["corr"].round(2)), ""]
    if out["spec"]["rebalance"] == "risk_parity" and len(out["weight_log"]):
        lines += ["## 연도별 배분 비중 (위험균형)", "", _md((out["weight_log"] * 100).round(1).set_index(out["weight_log"].index.year)), ""]
    yr = pd.DataFrame({n: out["equities"][n].resample("YE").last().pct_change() for n in out["names"]})
    yr["portfolio"] = out["portfolio"].resample("YE").last().pct_change()
    first = {n: out["equities"][n].resample("YE").last().iloc[0] / out["equities"][n].iloc[0] - 1 for n in out["names"]}
    first["portfolio"] = out["portfolio"].resample("YE").last().iloc[0] / out["portfolio"].iloc[0] - 1
    yr.iloc[0] = pd.Series(first)
    yr.index = yr.index.year
    lines += ["## 연도별 수익률 (%)", "", _md((yr * 100).round(1)), ""]
    return "\n".join(lines)


def write(spec_path, out_dir="reports/portfolio") -> dict:
    spec = load_portfolio(spec_path); out = run_portfolio(spec)
    d = Path(out_dir); d.mkdir(parents=True, exist_ok=True)
    name = spec.get("name", Path(spec_path).stem)
    (d / f"{name}.md").write_text(render(out, name), encoding="utf-8")
    pd.concat([out["equities"], out["portfolio"]], axis=1).to_csv(d / f"{name}_equity.csv")
    combined_orders(out).to_csv(d / f"{name}_orders.csv", index=False)
    return out
