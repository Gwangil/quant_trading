"""전략 레지스트리. YAML 최상위 `kind` 로 전략 종류를 고른다.

  basket_loc  분할 바스켓 LOC (engine.py, config.StrategyConfig) — 기본
  trend       추세추종 + 변동성 타게팅 (strategies/trend.py)
새 전략 추가: strategies/<name>.py 에 Config dataclass + Strategy(prepare/orders) 구현 후 아래 KINDS 에 등록.
"""
from __future__ import annotations

from pathlib import Path

import yaml


def load_any(path):
    """kind 에 맞는 설정 객체를 돌려준다."""
    raw = yaml.safe_load(open(path, encoding="utf-8")) or {}
    kind = raw.pop("kind", "basket_loc")
    return KINDS[kind]["config"](raw), kind


def run_any(cfg, kind: str, data=None):
    return KINDS[kind]["run"](cfg, data)


def _basket_config(raw):
    from ..config import config_from_dict
    return config_from_dict(raw)


def _basket_run(cfg, data=None):
    from ..engine import run_backtest
    return run_backtest(cfg, data)


def _trend_config(raw):
    from .trend import trend_config_from_dict
    return trend_config_from_dict(raw)


def _trend_run(cfg, data=None):
    from .trend import run_trend
    return run_trend(cfg, data)


KINDS = {
    "basket_loc": {"config": _basket_config, "run": _basket_run, "desc": "분할 바스켓 LOC (하락 매수·반등 매도, 평균회귀형)"},
    "trend": {"config": _trend_config, "run": _trend_run, "desc": "추세추종: 기준지수 이평 위 + 모멘텀 양이면 보유, 변동성 타게팅, 추적 손절 (추세형)"},
}
