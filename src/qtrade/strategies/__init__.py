"""전략 레지스트리. YAML 최상위 `kind` 로 전략 종류를 고른다.

  basket_loc  분할 바스켓 LOC (engine.py, config.StrategyConfig) — 기본
  trend       추세추종 + 변동성 타게팅 (strategies/trend.py)
  regime_switch  기준지수 국면(약세/강세)에 따라 자산 보유 ↔ 현금 (strategies/regime_switch.py)
  v5_scalp    invest_strategy v5 변동성 수확 (고정 예산 단리, reference.py 래퍼)
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


def _switch_config(raw):
    from .regime_switch import switch_config_from_dict
    return switch_config_from_dict(raw)


def _switch_run(cfg, data=None):
    from .regime_switch import run_switch
    return run_switch(cfg, data)


def _v5_config(raw):
    from .v5_scalp import v5_config_from_dict
    return v5_config_from_dict(raw)


def _v5_run(cfg, data=None):
    from .v5_scalp import run_v5
    return run_v5(cfg, data)


KINDS = {
    "basket_loc": {"config": _basket_config, "run": _basket_run, "desc": "분할 바스켓 LOC (하락 매수·반등 매도, 평균회귀형)"},
    "trend": {"config": _trend_config, "run": _trend_run, "desc": "추세추종: 기준지수 이평 위 + 모멘텀 양이면 보유, 변동성 타게팅, 추적 손절 (추세형)"},
    "regime_switch": {"config": _switch_config, "run": _switch_run, "desc": "국면 스위치: 기준지수 약세(또는 강세) 국면에만 자산 보유 (약세 국면 자산 검증용)"},
    "v5_scalp": {"config": _v5_config, "run": _v5_run, "desc": "변동성 수확 v5: 하락일 매수·상승일 부분매도·익절 1.5%·40일 청산·계좌 브레이커 (단리)"},
}
