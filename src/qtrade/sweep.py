"""파라미터 그리드 탐색 + 학습/검증 구간 분리(walk-forward 간이형)."""
from __future__ import annotations

import itertools
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd
import yaml

from .config import StrategyConfig
from .engine import run_backtest, prepare_frame
from .metrics import compute_metrics

_METRIC_KEYS = ["simple_annual", "cagr", "mdd", "mdd_recover_days", "max_underwater_days", "sharpe",
                "calmar", "worst_year", "worst_month", "ulcer_index", "pct_days_dd_gt20", "avg_exposure", "n_baskets_closed", "basket_win_rate", "n_trades"]

_DATA: pd.DataFrame | None = None


def _init(data: pd.DataFrame):
    global _DATA
    _DATA = data


def _slice_metrics(equity: pd.Series, exposure: pd.Series, split: str | None) -> dict:
    out = {}
    if split is None:
        return out
    s = pd.Timestamp(split)
    for tag, seg in (("train", equity[equity.index < s]), ("test", equity[equity.index >= s])):
        if len(seg) > 30:
            mm = compute_metrics(seg, exposure.reindex(seg.index))
            for k in ("simple_annual", "cagr", "mdd", "calmar", "sharpe"):
                out[f"{tag}_{k}"] = mm.get(k)
    return out


def _run_one(args):
    base_dict, overrides, split = args
    from .config import config_from_dict
    cfg = config_from_dict(base_dict).with_overrides(overrides)
    res = run_backtest(cfg, _DATA)
    m = compute_metrics(res.equity, res.frame["exposure"], res.baskets, res.trades)
    row = dict(overrides)
    row.update({k: m.get(k) for k in _METRIC_KEYS})
    row.update(_slice_metrics(res.equity, res.frame["exposure"], split))
    return row


def expand_grid(grid: dict[str, list]) -> list[dict]:
    keys = list(grid)
    return [dict(zip(keys, vals)) for vals in itertools.product(*[grid[k] for k in keys])]


def run_sweep(base: StrategyConfig, grid: dict[str, list], split: str | None = None,
              workers: int | None = None, data: pd.DataFrame | None = None) -> pd.DataFrame:
    from .data import build_dataset
    data = data if data is not None else build_dataset(base.data)
    combos = expand_grid(grid)
    base_dict = base.to_dict()
    jobs = [(base_dict, c, split) for c in combos]
    rows = []
    if workers == 1 or len(jobs) <= 2:
        _init(data)
        rows = [_run_one(j) for j in jobs]
    else:
        with ProcessPoolExecutor(max_workers=workers, initializer=_init, initargs=(data,)) as ex:
            rows = list(ex.map(_run_one, jobs, chunksize=4))
    return pd.DataFrame(rows)


def rank(df: pd.DataFrame, max_mdd: float = -0.40, by: str = "simple_annual") -> pd.DataFrame:
    """MDD 제약(예: −40% 이내)을 만족하는 조합을 목표 지표로 정렬."""
    ok = df[df["mdd"] >= max_mdd].copy() if "mdd" in df else df.copy()
    return ok.sort_values(by, ascending=False)


def load_grid(path: str | Path) -> tuple[dict, dict]:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return raw.get("grid", {}), {k: v for k, v in raw.items() if k != "grid"}
