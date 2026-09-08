"""전략 프로필(방어형/균형형/공격형)의 단일 원천. configs/*.yaml 은 `qtrade make-configs` 로 생성한다.

실제 SOXL 하이브리드 스냅샷(2001~2026, IS ~2017 / OOS 2018~)으로 재탐색한 값. 근거: docs/02_backtest_results.md
"""
from __future__ import annotations

from .config import StrategyConfig, config_from_dict

# 세 프로필이 공유하는 코어 규칙 (실데이터 탐색에서 안정적으로 우위였던 값)
CORE = {
    "initial_capital": 100_000,
    # 현금 파킹: 대기 현금의 80% 를 단기채 ETF(SGOV/BIL 류)에 두는 가정. 수익률은 번들 3개월 T-bill 연평균 표, 보수 0.15%
    "cash_yield_annual": "TBILL3M",
    "cash_yield_fraction": 0.8,
    "cash_yield_spread": -0.0015,
    "baskets": {"count": 4, "slices": 6, "min_days_between_opens": 3, "min_budget_frac": 0.25,
                "budget_frac": None, "budget_mode": "equity"},
    "entry": {"vol_window": 20, "dip_vol_mult": 0.25, "min_dip_pct": 0.0, "max_dip_pct": 0.06,
              "first_slice_dip_pct": 0.0, "first_slice_mult": 1.0, "depth_boost": 0.0, "max_slice_mult": 3.0,
              "target_vol": 0.045},
    "exit": {"lot_tp_vol_mult": 1.0, "min_lot_tp_pct": 0.03, "max_lot_tp_pct": 0.15, "lot_tp_sell_frac": 1.0,
             "upday_sell_frac": 0.1, "upday_min_rise": 0.0,
             "basket_tp_pct": 0.20, "basket_sl_pct": None, "max_hold_days": 60, "hard_max_hold_days": 120,
             "soft_exit_pnl_pct": 0.0},
    "regime": {"enabled": True, "ma_window": 200, "ma_band": 0.02, "bear_max_baskets": 1, "bear_slice_mult": 0.5,
               "bear_no_new_lots": False, "bear_liquidate": True, "cooldown_after_sl_days": 20,
               "max_vol_to_open": None, "breaker_dd": None, "breaker_resume_sma": 200},
    "risk": {"vol_target_annual": None, "max_exposure": 1.0, "dd_scale_start": None,
             "dd_scale_floor": 0.30, "dd_scale_min_mult": 0.25},
    "costs": {"commission_pct": 0.001, "slippage_pct": 0.0},
}

# 프로필별 차이 (점 표기 오버라이드)
PROFILES = {
    "defensive": {"exit.upday_sell_frac": 0.2, "risk.vol_target_annual": 0.30},
    "balanced": {},
    "aggressive": {"baskets.slices": 4, "regime.breaker_dd": 0.25, "regime.ma_band": 0.02},
}

PROFILE_DESC = {
    "defensive": "방어형: 상승일 부분매도 20% + 연 30% 변동성 타게팅 노출상한. MDD·낙폭 체류를 최소화",
    "balanced": "균형형(기본): 상승일 부분매도 10%, 노출상한 없음",
    "aggressive": "공격형: 슬라이스 4(빠른 투입) + 계좌 서킷브레이커 −25%. 수익 우선, MDD −40%대 감수",
}

DATA = {
    "live": {"symbol": "SOXL", "reference": "SOXX", "source": "csv", "start": "2011-01-03", "end": None,
             "backfill": False, "synthetic": None},   # data/cache/*.csv ← `qtrade data update`
    "hybrid": {"symbol": "SOXL", "reference": "SOXX", "source": "bundled", "start": None, "end": None,
               "backfill": False, "synthetic": None},
    "proxy": {"symbol": "NASDAQ3X", "reference": "NASDAQ", "source": "bundled", "start": None, "end": None,
              "backfill": False, "synthetic": {"leverage": 3, "beta": 1.0, "expense_ratio": 0.0095, "financing_rate": 0.02}},
}


def build(profile: str, data: str = "hybrid", name: str | None = None) -> StrategyConfig:
    import copy
    raw = copy.deepcopy(CORE)
    raw["name"] = name or f"soxl_{profile}"
    raw["data"] = copy.deepcopy(DATA[data])
    return config_from_dict(raw).with_overrides(PROFILES[profile])


def write_all(out_dir: str = "configs") -> list[str]:
    from pathlib import Path
    from .config import save_config
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    written = []
    for profile in PROFILES:
        for data, suffix in (("live", ""), ("hybrid", "_hybrid"), ("proxy", "_proxy")):
            name = f"soxl_{profile}{suffix}" if data != "proxy" else f"nasdaq3x_{profile}"
            cfg = build(profile, data, name)
            path = out / f"{name}.yaml"
            header = f"# 자동 생성 (qtrade make-configs). 수정은 src/qtrade/profiles.py 에서.\n# {PROFILE_DESC[profile]}\n# 데이터: {data} ({cfg.data.symbol}/{cfg.data.reference}, {cfg.data.source})\n"
            save_config(cfg, path)
            path.write_text(header + path.read_text(encoding="utf-8"), encoding="utf-8")
            written.append(str(path))
    return written
