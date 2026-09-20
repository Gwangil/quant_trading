"""국면 스위치 슬리브: 기준지수의 이평 국면에 따라 자산을 들거나 현금(파킹)으로 간다.

  hold_when: bear  → 기준지수 < SMA×(1−band) 일 때 symbol 보유 (약세 국면 자산: GLD, 단기채 ETF, 인버스 등)
  hold_when: bull  → 기준지수 > SMA×(1+band) 일 때 보유
비중은 weight(고정) 또는 변동성 타게팅(target_vol_annual). MOC 체결. 바스켓 슬리브가 약세장에서 비워 두는 자본의 용도를 검증하기 위한 전략.
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
class SwitchRules:
    hold_when: str = "bear"          # bear | bull | always (상시 보유 = 매수 후 보유, 비교용)
    ma_window: int = 200
    band: float = 0.02               # 진입·청산 히스테리시스
    weight: float = 1.0
    target_vol_annual: float | None = None
    rebalance_band: float = 0.15
    vol_window: int = 20
    min_hold_days: int = 5           # 진입 후 최소 보유 (whipsaw 완화)


@dataclass
class SwitchConfig:
    name: str = "switch"
    initial_capital: float = 100_000.0
    cash_yield_annual: float | str = "TBILL3M"
    cash_yield_fraction: float = 0.8
    cash_yield_spread: float = -0.0015
    data: DataConfig = field(default_factory=DataConfig)
    rules: SwitchRules = field(default_factory=SwitchRules)
    costs: CostConfig = field(default_factory=CostConfig)

    def to_dict(self):
        from dataclasses import asdict
        d = asdict(self); d["kind"] = "regime_switch"; return d

    def with_overrides(self, overrides: dict):
        import copy
        cfg = copy.deepcopy(self)
        for path, v in overrides.items():
            obj = cfg; parts = path.split(".")
            for p in parts[:-1]: obj = getattr(obj, p)
            if not hasattr(obj, parts[-1]): raise KeyError(path)
            setattr(obj, parts[-1], v)
        return cfg


def switch_config_from_dict(raw: dict) -> SwitchConfig:
    raw = dict(raw)
    kw = {"data": _build(DataConfig, raw.pop("data", None)), "rules": _build(SwitchRules, raw.pop("rules", None)),
          "costs": _build(CostConfig, raw.pop("costs", None))}
    valid = {f.name for f in fields(SwitchConfig)}
    for k, v in raw.items():
        if k not in valid: raise KeyError(f"SwitchConfig: unknown key '{k}'")
        kw[k] = v
    return SwitchConfig(**kw)


class SwitchStrategy:
    def __init__(self, cfg: SwitchConfig):
        self.cfg = cfg; self.r = cfg.rules; self._state = None   # True = 보유 국면

    def prepare(self, df):
        r = self.r
        ma = sma(df["ref_close"], r.ma_window); df["ma"] = ma
        df["vol"] = realized_vol(df["close"], r.vol_window)
        df["bull"] = (df["ref_close"] > ma).fillna(False)
        df["ready"] = ma.notna() & df["vol"].notna()
        return df

    def _target_weight(self, vol):
        r = self.r
        if r.target_vol_annual and vol == vol and vol > 0:
            return min(r.weight, r.target_vol_annual / (vol * np.sqrt(TRADING_DAYS)))
        return r.weight

    def orders(self, i, df, st):
        r = self.r
        px, ref, ma, vol = df["close"].iat[i], df["ref_close"].iat[i], df["ma"].iat[i], df["vol"].iat[i]
        if ma != ma: return []
        # 히스테리시스 국면 판정
        if r.hold_when == "always":
            self._state = True
        elif self._state is None:
            self._state = (ref < ma) if r.hold_when == "bear" else (ref > ma)
        elif r.hold_when == "bear":
            if self._state and ref > ma * (1 + r.band): self._state = False
            elif not self._state and ref < ma * (1 - r.band): self._state = True
        else:
            if self._state and ref < ma * (1 - r.band): self._state = False
            elif not self._state and ref > ma * (1 + r.band): self._state = True
        holding = st.shares > 0
        if self._state:
            w = self._target_weight(vol); cur = st.shares * px / st.equity if st.equity > 0 else 0.0
            if not holding:
                return [Order(0, "BUY", "MOC", w * st.equity / px, None, "switch_entry")]
            if abs(w - cur) > r.rebalance_band:
                d = (w - cur) * st.equity
                return [Order(0, "BUY" if d > 0 else "SELL", "MOC", abs(d) / px, None, "rebalance")]
            return []
        if holding and (st.entry_idx is None or i - st.entry_idx >= r.min_hold_days):
            return [Order(0, "SELL", "MOC", st.shares, None, "switch_exit")]
        return []


def run_switch(cfg: SwitchConfig, data=None):
    from ..sim import run_sim
    data = data if data is not None else build_dataset(cfg.data)
    return run_sim(cfg, SwitchStrategy(cfg), data)
