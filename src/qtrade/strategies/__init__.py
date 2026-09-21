"""전략 레지스트리. YAML 최상위 `kind` 로 전략 종류를 고른다.

  basket_loc     분할 바스켓 LOC (engine.py, config.StrategyConfig) — 핵심 전략
  regime_switch  자산 상시 보유 / 기준지수 국면별 보유 (strategies/regime_switch.py) — GLD 슬리브용
새 전략 추가: strategies/<name>.py 에 Config dataclass + Strategy(prepare/orders) 구현 후 아래 KINDS 에 등록 (docs/07 §2).
기각된 kind(추세추종 trend, v5 변동성 수확 v5_scalp)는 2026-09-21 정리 시 제거. 결과는 docs/07 §4.
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


def _switch_config(raw):
    from .regime_switch import switch_config_from_dict
    return switch_config_from_dict(raw)


def _switch_run(cfg, data=None):
    from .regime_switch import run_switch
    return run_switch(cfg, data)


KINDS = {
    "basket_loc": {"config": _basket_config, "run": _basket_run, "desc": "분할 바스켓 LOC (하락 매수·반등 매도, 평균회귀형)"},
    "regime_switch": {"config": _switch_config, "run": _switch_run, "desc": "국면 스위치: 기준지수 약세(또는 강세) 국면에만 자산 보유 (약세 국면 자산 검증용)"},
}
