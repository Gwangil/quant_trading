"""롤링 워크포워드: 여러 검증 창에서 파라미터를 재선정하고, 선정된 파라미터의 다음 창 성과를 이어붙인다.

방식
- 그리드의 각 조합을 전 구간에 대해 1회 실행(경로 의존 상태 포함)하고, 창별로 자산곡선을 잘라 지표를 낸다.
  → "그 파라미터로 처음부터 운용해 왔다면 이 창에서 어땠나"를 뜻한다.
- 창 k 의 학습 구간 = 데이터 시작 ~ 창 k 시작 전날(확장형). 목적함수(기본: 학습 MDD ≥ 게이트 → Calmar 최대)로 조합을 고른다.
- 선정 조합의 창 k 검증 구간 수익률을 이어붙인 것이 워크포워드 OOS 곡선이다.
"""
from __future__ import annotations

import itertools
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from .config import StrategyConfig, config_from_dict
from .data import build_dataset
from .engine import run_backtest
from .metrics import compute_metrics

_DATA: pd.DataFrame | None = None


def _init(data):
    global _DATA
    _DATA = data


def _run(args):
    base, over = args
    cfg = config_from_dict(base).with_overrides(over)
    res = run_backtest(cfg, _DATA)
    return over, res.equity


def expand(grid: dict) -> list[dict]:
    keys = list(grid)
    return [dict(zip(keys, v)) for v in itertools.product(*[grid[k] for k in keys])]


def run_all(base: StrategyConfig, grid: dict, workers: int | None = None, data=None) -> list[tuple[dict, pd.Series]]:
    data = data if data is not None else build_dataset(base.data)
    jobs = [(base.to_dict(), o) for o in expand(grid)]
    with ProcessPoolExecutor(max_workers=workers, initializer=_init, initargs=(data,)) as ex:
        return list(ex.map(_run, jobs, chunksize=4))


def _seg(eq: pd.Series, start, end) -> pd.Series:
    s = eq
    if start: s = s[s.index >= pd.Timestamp(start)]
    if end: s = s[s.index <= pd.Timestamp(end)]
    return s


def select(results, train_end, mdd_gate=-0.40, by="calmar") -> tuple[dict, dict]:
    """학습 구간(~train_end) 지표로 최선 조합 선택. 게이트 통과 조합이 없으면 MDD 가 가장 얕은 조합."""
    scored = []
    for over, eq in results:
        m = compute_metrics(_seg(eq, None, train_end))
        scored.append((over, m))
    ok = [x for x in scored if x[1]["mdd"] >= mdd_gate]
    if ok:
        best = max(ok, key=lambda x: (x[1][by] if x[1][by] == x[1][by] else -1e9))
    else:
        best = max(scored, key=lambda x: x[1]["mdd"])
    return best


def walk_forward(base: StrategyConfig, grid: dict, windows: list[tuple[str, str]], mdd_gate=-0.40, by="calmar",
                 workers=None, data=None, fixed: dict | None = None) -> dict:
    """windows: [(test_start, test_end), ...] 시간순. fixed: 비교용 고정 파라미터(예: 균형형 = {})."""
    results = run_all(base, grid, workers, data)
    rows, stitched = [], []
    fixed_eq = None
    if fixed is not None:
        fixed_eq = next((eq for o, eq in results if o == fixed), None)
        if fixed_eq is None:
            fixed_eq = run_backtest(base.with_overrides(fixed), data if data is not None else build_dataset(base.data)).equity
    for ts, te in windows:
        train_end = (pd.Timestamp(ts) - pd.Timedelta(days=1)).date().isoformat()
        over, mtr = select(results, train_end, mdd_gate, by)
        eq = next(e for o, e in results if o == over)
        test = _seg(eq, ts, te)
        mte = compute_metrics(test)
        row = {"test_start": ts, "test_end": te, **{f"p:{k}": v for k, v in over.items()},
               "train_cagr": mtr["cagr"], "train_mdd": mtr["mdd"], "train_calmar": mtr["calmar"],
               "test_cagr": mte["cagr"], "test_mdd": mte["mdd"], "test_calmar": mte["calmar"], "test_worst_year": mte["worst_year"]}
        if fixed_eq is not None:
            mf = compute_metrics(_seg(fixed_eq, ts, te))
            row.update({"fixed_test_cagr": mf["cagr"], "fixed_test_mdd": mf["mdd"], "fixed_test_calmar": mf["calmar"]})
        rows.append(row)
        stitched.append(test.pct_change().fillna(0.0))
    r = pd.concat(stitched)
    r = r[~r.index.duplicated(keep="first")]
    wf_eq = (1 + r).cumprod() * base.initial_capital
    out = {"table": pd.DataFrame(rows), "wf_equity": wf_eq, "wf_metrics": compute_metrics(wf_eq)}
    if fixed_eq is not None:
        f = _seg(fixed_eq, windows[0][0], windows[-1][1])
        out["fixed_metrics"] = compute_metrics(f)
        out["fixed_equity"] = f
    # 파라미터 안정성: 창별 선정값 변화
    pcols = [c for c in out["table"].columns if c.startswith("p:")]
    out["stability"] = {c[2:]: out["table"][c].astype(str).tolist() for c in pcols}
    return out


DEFAULT_WINDOWS = [("2006-01-01", "2009-12-31"), ("2010-01-01", "2013-12-31"), ("2014-01-01", "2017-12-31"),
                   ("2018-01-01", "2021-12-31"), ("2022-01-01", "2026-12-31")]


def render(out: dict, title="롤링 워크포워드") -> str:
    t = out["table"]
    pcols = [c for c in t.columns if c.startswith("p:")]
    lines = [f"# {title}", "", "| 검증 창 | " + " | ".join(c[2:] for c in pcols) + " | 학습 CAGR / MDD | 검증 CAGR / MDD / Calmar | 고정(균형형) 검증 CAGR / MDD |", "|---|" + "---|" * (len(pcols) + 3)]
    for _, r in t.iterrows():
        fx = f"{r.get('fixed_test_cagr', float('nan')):.1%} / {r.get('fixed_test_mdd', float('nan')):.1%}" if "fixed_test_cagr" in r else "-"
        lines.append(f"| {r.test_start[:4]}~{r.test_end[:4]} | " + " | ".join(str(r[c]) for c in pcols) +
                     f" | {r.train_cagr:.1%} / {r.train_mdd:.1%} | {r.test_cagr:.1%} / {r.test_mdd:.1%} / {r.test_calmar:.2f} | {fx} |")
    m = out["wf_metrics"]
    lines += ["", f"- 워크포워드 OOS 이어붙임: CAGR {m['cagr']:.1%}, MDD {m['mdd']:.1%}, Calmar {m['calmar']:.2f}, 최악 연도 {m['worst_year']:.1%}"]
    if "fixed_metrics" in out:
        f = out["fixed_metrics"]
        lines.append(f"- 고정 파라미터(균형형) 같은 구간: CAGR {f['cagr']:.1%}, MDD {f['mdd']:.1%}, Calmar {f['calmar']:.2f}, 최악 연도 {f['worst_year']:.1%}")
    return "\n".join(lines)
