"""추세추종 전략 (바스켓 전략의 상보 슬리브).

규칙 (모두 당일 종가로 판단, 다음 거래일 종가 MOC 체결)
- 진입: 기준지수 종가 > SMA(ma_window) 이고 매매대상 mom_window 일 수익률 > 0.
- 청산: 기준지수 종가 < SMA×(1−exit_band) 이거나, 매매대상이 진입 후 고점 대비 trail_pct 하락, 또는 모멘텀 음전환(옵션).
- 규모: 목표 연변동성 / 실현 연변동성 (상한 max_weight). 목표 비중과 현재 비중 차이가 rebalance_band 를 넘을 때만 리밸런싱.
- 재진입 쿨다운: 청산 후 cooldown_days 동안 재진입 금지 (whipsaw 완화).
바스켓 전략이 하락에 사고 반등에 파는 동안(평균 노출 16%), 이 전략은 상승 추세에서 노출을 유지한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields

import numpy as np
import pandas as pd

from ..config import DataConfig, CostConfig, _build
from ..data import build_dataset, TRADING_DAYS
from ..indicators import realized_vol, sma
from ..strategy import Order


@dataclass
class TrendRules:
    ma_window: int = 200
    exit_band: float = 0.02          # 이평 아래 이 비율까지 내려가야 청산 (히스테리시스)
    mom_window: int = 60             # 모멘텀 창(거래일)
    exit_on_mom_negative: bool = False
    trail_pct: float = 0.25          # 진입 후 고점 대비 추적 손절
    vol_window: int = 20
    target_vol_annual: float = 0.40  # 목표 연변동성 (SOXL 실현 60~100% → 비중 40~65%)
    max_weight: float = 1.0
    rebalance_band: float = 0.15     # |목표비중 − 현재비중| > band 일 때만 리밸런싱
    cooldown_days: int = 10


@dataclass
class TrendConfig:
    name: str = "trend_soxl"
    initial_capital: float = 100_000.0
    cash_yield_annual: float | str = "TBILL3M"
    cash_yield_fraction: float = 0.8
    cash_yield_spread: float = -0.0015
    data: DataConfig = field(default_factory=DataConfig)
    rules: TrendRules = field(default_factory=TrendRules)
    costs: CostConfig = field(default_factory=CostConfig)

    def to_dict(self):
        from dataclasses import asdict
        d = asdict(self); d["kind"] = "trend"; return d

    def with_overrides(self, overrides: dict):
        import copy
        cfg = copy.deepcopy(self)
        for path, v in overrides.items():
            obj = cfg; parts = path.split(".")
            for p in parts[:-1]: obj = getattr(obj, p)
            if not hasattr(obj, parts[-1]): raise KeyError(path)
            setattr(obj, parts[-1], v)
        return cfg


def trend_config_from_dict(raw: dict) -> TrendConfig:
    raw = dict(raw)
    kw = {"data": _build(DataConfig, raw.pop("data", None)), "rules": _build(TrendRules, raw.pop("rules", None)),
          "costs": _build(CostConfig, raw.pop("costs", None))}
    valid = {f.name for f in fields(TrendConfig)}
    for k, v in raw.items():
        if k not in valid: raise KeyError(f"TrendConfig: unknown key '{k}'")
        kw[k] = v
    return TrendConfig(**kw)


class TrendStrategy:
    def __init__(self, cfg: TrendConfig):
        self.cfg = cfg; self.r = cfg.rules
        self._last_exit: int | None = None

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        r = self.r
        ma = sma(df["ref_close"], r.ma_window)
        df["ma"] = ma
        df["mom"] = df["close"].pct_change(r.mom_window)
        df["vol"] = realized_vol(df["close"], r.vol_window)
        df["bull"] = (df["ref_close"] > ma).fillna(False)
        df["ready"] = ma.notna() & df["mom"].notna() & df["vol"].notna()
        return df

    def orders(self, i, df, st) -> list[Order]:
        r = self.r
        px = df["close"].iat[i]; ref = df["ref_close"].iat[i]; ma = df["ma"].iat[i]
        mom = df["mom"].iat[i]; vol = df["vol"].iat[i]
        if not (ma == ma and vol == vol and mom == mom):
            return []
        holding = st.shares > 0
        if holding:
            exit_ = ref < ma * (1 - r.exit_band) or px < st.high_since_entry * (1 - r.trail_pct) or (r.exit_on_mom_negative and mom < 0)
            if exit_:
                self._last_exit = i
                return [Order(0, "SELL", "MOC", st.shares, None, "trend_exit")]
            target_w = min(r.max_weight, r.target_vol_annual / (vol * np.sqrt(TRADING_DAYS))) if vol > 0 else r.max_weight
            cur_w = st.shares * px / st.equity if st.equity > 0 else 0.0
            if abs(target_w - cur_w) > r.rebalance_band:
                delta_val = (target_w - cur_w) * st.equity
                qty = abs(delta_val) / px
                return [Order(0, "BUY" if delta_val > 0 else "SELL", "MOC", qty, None, "rebalance")]
            return []
        if self._last_exit is not None and i - self._last_exit < r.cooldown_days:
            return []
        if ref > ma and mom > 0:
            w = min(r.max_weight, r.target_vol_annual / (vol * np.sqrt(TRADING_DAYS))) if vol > 0 else r.max_weight
            return [Order(0, "BUY", "MOC", w * st.equity / px, None, "trend_entry")]
        return []


def run_trend(cfg: TrendConfig, data: pd.DataFrame | None = None):
    from ..sim import run_sim
    data = data if data is not None else build_dataset(cfg.data)
    return run_sim(cfg, TrendStrategy(cfg), data)
