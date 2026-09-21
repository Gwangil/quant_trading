"""변동성 수확 슬리브: invest_strategy v5(고정 예산 단리 바구니 스캘퍼)를 kind 로 감싼 것.

시뮬레이션은 reference.run_reference_full(원본과 동등성 검증됨)을 그대로 쓰고, 마지막 상태에서 다음 거래일 주문을
원본 규칙과 같은 뜻의 LOC/MOC 로 만든다:
  보유 ≥ max_hold_days      → SELL MOC 전량
  상승일 부분매도            → SELL LOC 지정가 = 전일종가 × (1+ε), 수량 = 보유 × partial_sell (익절 미달 구간)
  익절                       → SELL LOC 지정가 = 평단 × (1+target)
  추가매수(평단 −5%)         → BUY  LOC 지정가 = 평단 × (1+addon_drop)
  신규 진입(전일 RSI<임계)   → BUY  LOC 지정가 = 종가 × (1+max_entry_rise)   (하락 마감 시 체결)
  서킷브레이커 발동 중       → 보유 있으면 SELL MOC, 신규 없음
단리(예산 고정)라 포트폴리오 슬리브로 쓸 때는 연 1회 리밸런싱이 사실상 예산 재설정 역할을 한다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, fields

import numpy as np
import pandas as pd

from ..config import DataConfig, CostConfig, _build
from ..data import build_dataset
from ..engine import BacktestResult
from ..reference import ReferenceParams, run_reference_full, rsi_sma
from ..strategy import Order


@dataclass
class V5Config:
    name: str = "v5_soxl"
    initial_capital: float = 100_000.0
    cash_yield_annual: float | str = 0.0     # 원본 비교와의 일관성을 위해 기본 0 (파킹은 슬리브 밖에서)
    cash_yield_fraction: float = 0.8
    cash_yield_spread: float = -0.0015
    data: DataConfig = field(default_factory=DataConfig)
    rules: ReferenceParams = field(default_factory=lambda: ReferenceParams(target_profit=0.015, breaker_dd=-0.15))
    costs: CostConfig = field(default_factory=CostConfig)

    def to_dict(self):
        from dataclasses import asdict
        d = asdict(self); d["kind"] = "v5_scalp"; return d

    def with_overrides(self, overrides: dict):
        import copy
        cfg = copy.deepcopy(self)
        for path, v in overrides.items():
            obj = cfg; parts = path.split(".")
            for q in parts[:-1]: obj = getattr(obj, q)
            if not hasattr(obj, parts[-1]): raise KeyError(path)
            setattr(obj, parts[-1], v)
        return cfg


def v5_config_from_dict(raw: dict) -> V5Config:
    raw = dict(raw)
    kw = {"data": _build(DataConfig, raw.pop("data", None)), "rules": _build(ReferenceParams, raw.pop("rules", None)),
          "costs": _build(CostConfig, raw.pop("costs", None))}
    valid = {f.name for f in fields(V5Config)}
    for k, v in raw.items():
        if k not in valid: raise KeyError(f"V5Config: unknown key '{k}'")
        kw[k] = v
    return V5Config(**kw)


def _pending_orders(r: dict, p: ReferenceParams, last_date: pd.Timestamp) -> list[Order]:
    px = r["last"]["close"]; orders: list[Order] = []
    if r["halted"]:
        for i, d in enumerate(r["divs"]):
            if d.active and d.shares > 0:
                orders.append(Order(i, "SELL", "MOC", float(d.shares), None, "breaker"))
        return orders
    any_free = False
    for i, d in enumerate(r["divs"]):
        if not d.active:
            any_free = True; continue
        held = (last_date - d.start).days if d.start is not None else 0
        if held + 1 >= p.max_hold_days:   # 다음 거래일에 보유일 도달
            orders.append(Order(i, "SELL", "MOC", float(d.shares), None, "max_hold")); continue
        profit = (px - d.avg) / d.avg if d.avg else 0.0
        if profit < p.target_profit:
            q = math.floor(d.shares * p.partial_sell)
            if q > 0: orders.append(Order(i, "SELL", "LOC", float(q), round(px * 1.0001, 4), "partial_sell"))
        orders.append(Order(i, "SELL", "LOC", float(d.shares), round(d.avg * (1 + p.target_profit), 4), "take_profit"))
        if d.cash > 100:
            lim = round(d.avg * (1 + p.addon_drop), 4)
            orders.append(Order(i, "BUY", "LOC", d.alloc * p.buy_ratio / lim, lim, "addon"))
    if any_free and r["last"]["rsi"] < p.rsi_max:
        lim = round(px * (1 + p.max_entry_rise), 4)
        free = next(i for i, d in enumerate(r["divs"]) if not d.active)
        orders.append(Order(free, "BUY", "LOC", r["divs"][free].alloc * p.buy_ratio / lim, lim, "entry"))
    return orders


def run_v5(cfg: V5Config, data: pd.DataFrame | None = None) -> BacktestResult:
    data = data if data is not None else build_dataset(cfg.data)
    p = cfg.rules; p.commission = cfg.costs.commission_pct
    close = data["close"]
    if cfg.data.start:
        close = close[close.index >= pd.Timestamp(cfg.data.start) - pd.Timedelta(days=60)]
    r = run_reference_full(close, cfg.initial_capital, p)
    rows = pd.DataFrame(r["rows"]).set_index("date")
    if cfg.data.start:
        rows = rows[rows.index >= pd.Timestamp(cfg.data.start)]
    rows["ref_close"] = data["ref_close"].reindex(rows.index)
    rows["vol"] = np.log(rows["close"]).diff().rolling(20).std()
    rows["bull"] = True; rows["interest"] = 0.0
    rows["exposure"] = rows["invested"] / rows["equity"]
    # 자본 재기준화: start 이후 첫날 자산을 initial_capital 로
    scale = cfg.initial_capital / rows["equity"].iloc[0]
    for c in ("cash", "invested", "equity"): rows[c] *= scale
    trades = pd.DataFrame(columns=["date", "basket", "side", "kind", "qty", "price", "value", "fee", "pnl", "reason", "lots"])
    baskets = pd.DataFrame(columns=["id", "opened", "closed", "status", "budget", "pnl", "ret", "n_buys", "n_sells", "hold_days", "reason"])
    res = BacktestResult(cfg=cfg, equity=rows["equity"].rename("equity"), frame=rows, trades=trades, baskets=baskets,
                         pending_orders=_pending_orders(r, p, rows.index[-1]), strategy=None, final_cash=float(rows["cash"].iloc[-1]))
    res.n_fillable_orders = r["n_fills"]
    return res
