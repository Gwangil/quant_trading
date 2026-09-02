"""분할 바스켓 LOC 전략의 상태(로트/바스켓)와 일간 의사결정 로직.

핵심 아이디어
- 자산을 N개의 바스켓(예산)으로 나누고, 각 바스켓은 독립적인 "한 라운드"를 돈다.
- 라운드 안에서는 매일 종가 기준으로
    · 떨어지면 산다: 매수 LOC 지정가 = 전일종가 × (1 − 하락률)   → 하락 마감일에만 체결
    · 오르면 판다:   로트별 매도 LOC 지정가 = 로트 매입가 × (1 + 목표율) → 반등 마감일에 체결
  하락률/목표율은 최근 변동성에 비례해 자동 조절된다.
- 바스켓은 (a) 예산 대비 목표수익 도달, (b) 손실 한도, (c) 보유기간 만료 중 하나로 전량 청산되고
  현금이 풀로 돌아와 다음 라운드를 시작한다 (주기적 청산 → 자금 회전).
- 기준 지수의 추세(이동평균)로 강세/약세를 나눠 약세장에서는 동시 바스켓 수와 매수 규모를 줄인다(MDD 관리).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from .config import StrategyConfig

Side = Literal["BUY", "SELL"]
Kind = Literal["LOC", "MOC"]


@dataclass
class Lot:
    qty: float
    cost: float          # 주당 매입가(수수료 제외)
    date: pd.Timestamp
    basket_id: int
    tp_done: bool = False   # 부분 익절 완료 → 이후 로트 익절 주문 없음(바스켓 청산까지 보유)


@dataclass
class Order:
    basket_id: int
    side: Side
    kind: Kind
    qty: float
    limit: float | None       # MOC 는 None
    reason: str
    lot_costs: tuple[float, ...] = ()   # SELL LOC 일 때 대상 로트 매입가 (체결 시 로트 매칭용)


@dataclass
class Basket:
    id: int
    budget: float
    opened: pd.Timestamp
    opened_idx: int
    lots: list[Lot] = field(default_factory=list)
    realized: float = 0.0        # 라운드 내 실현손익(수수료 차감)
    n_buys: int = 0
    n_sells: int = 0
    status: str = "active"       # active | liquidating | closed
    close_reason: str | None = None
    closed: pd.Timestamp | None = None
    hold_days_at_close: int | None = None

    # ---- 계산 ----
    def cost_basis(self) -> float:
        return sum(l.qty * l.cost for l in self.lots)

    def shares(self) -> float:
        return sum(l.qty for l in self.lots)

    def avg_cost(self) -> float | None:
        s = self.shares()
        return self.cost_basis() / s if s > 0 else None

    def market_value(self, price: float) -> float:
        return self.shares() * price

    def cash_avail(self) -> float:
        """바스켓이 추가 매수에 쓸 수 있는 현금 = 예산 − 보유 로트 원가 + 실현손익."""
        return self.budget - self.cost_basis() + self.realized

    def pnl(self, price: float) -> float:
        return self.realized + self.market_value(price) - self.cost_basis()

    def ret(self, price: float) -> float:
        return self.pnl(price) / self.budget if self.budget > 0 else 0.0

    def equity(self, price: float) -> float:
        return self.budget + self.pnl(price)


class BasketStrategy:
    """상태를 갖고 매일 주문을 생성. 체결 반영은 engine 이 담당."""

    def __init__(self, cfg: StrategyConfig):
        self.cfg = cfg
        self.baskets: list[Basket] = []
        self._next_id = 1
        self._last_open_idx: int | None = None
        self._last_sl_idx: int | None = None
        self._vol: float = 0.0

    # ---- 조회 ----
    def active_baskets(self) -> list[Basket]:
        return [b for b in self.baskets if b.status in ("active", "liquidating")]

    def reserved_cash(self) -> float:
        return sum(max(b.cash_avail(), 0.0) for b in self.active_baskets())

    # ---- 규모/가격 규칙 ----
    def dip_pct(self, vol: float, first: bool) -> float:
        e = self.cfg.entry
        if first:
            return e.first_slice_dip_pct
        return min(max(e.dip_vol_mult * vol, e.min_dip_pct), e.max_dip_pct)

    def lot_tp_pct(self, vol: float) -> float:
        x = self.cfg.exit
        return min(max(x.lot_tp_vol_mult * vol, x.min_lot_tp_pct), x.max_lot_tp_pct)

    def slice_mult(self, b: Basket, price: float, bull: bool) -> float:
        e = self.cfg.entry
        m = 1.0
        avg = b.avg_cost()
        if e.depth_boost > 0 and avg and price < avg:
            depth = (avg - price) / avg          # 평단 대비 하락폭
            m += e.depth_boost * (depth / 0.10)  # −10% 당 depth_boost 가산
        if not bull and self.cfg.regime.enabled:
            m *= self.cfg.regime.bear_slice_mult
        if e.target_vol is not None and self._vol and self._vol > e.target_vol:
            m *= e.target_vol / self._vol
        return min(m, e.max_slice_mult)

    # ---- 바스켓 라이프사이클 ----
    def maybe_open_basket(self, idx: int, date: pd.Timestamp, equity: float,
                          idle_cash: float, bull: bool, vol: float = 0.0) -> Basket | None:
        bc, rc = self.cfg.baskets, self.cfg.regime
        if rc.enabled and rc.max_vol_to_open is not None and vol > rc.max_vol_to_open:
            return None
        if (rc.enabled and rc.cooldown_after_sl_days > 0 and self._last_sl_idx is not None
                and idx - self._last_sl_idx < rc.cooldown_after_sl_days):
            return None
        max_active = bc.count
        if rc.enabled and not bull:
            max_active = min(max_active, rc.bear_max_baskets)
        if len(self.active_baskets()) >= max_active:
            return None
        if self._last_open_idx is not None and idx - self._last_open_idx < bc.min_days_between_opens:
            return None
        nominal = equity * (bc.budget_frac if bc.budget_frac else 1.0 / bc.count)
        budget = min(nominal, idle_cash)
        if budget < nominal * bc.min_budget_frac or budget <= 0:
            return None
        b = Basket(id=self._next_id, budget=budget, opened=date, opened_idx=idx)
        self._next_id += 1
        self.baskets.append(b)
        self._last_open_idx = idx
        return b

    def exit_reason(self, b: Basket, idx: int, price: float) -> str | None:
        x = self.cfg.exit
        hold = idx - b.opened_idx
        r = b.ret(price)
        if r >= x.basket_tp_pct:
            return "basket_tp"
        if x.basket_sl_pct is not None and r <= -x.basket_sl_pct:
            return "basket_sl"
        if hold >= x.hard_max_hold_days:
            return "time_hard"
        if hold >= x.max_hold_days and r >= x.soft_exit_pnl_pct:
            return "time_soft"
        return None

    def close_basket(self, b: Basket, date: pd.Timestamp, idx: int, reason: str) -> float:
        """로트가 없는 바스켓을 닫고 반환 현금(예산+손익)을 돌려준다."""
        assert not b.lots, "close_basket requires no open lots"
        b.status = "closed"
        b.close_reason = reason
        b.closed = date
        b.hold_days_at_close = idx - b.opened_idx
        return b.budget + b.realized

    # ---- 일간 주문 생성 (idx 일 종가 정보로 idx+1 일 종가 주문) ----
    def generate_orders(self, idx: int, date: pd.Timestamp, price: float, vol: float,
                        bull: bool, equity: float, idle_cash: float) -> tuple[list[Order], float]:
        """반환: (주문 리스트, 즉시 청산된 바스켓의 반환 현금 합계)."""
        orders: list[Order] = []
        returned = 0.0
        cfg = self.cfg
        self._vol = float(vol) if vol == vol else 0.0

        # 0) 약세 전환 시 초과 바스켓 청산 (수익률 낮은 순)
        forced: set[int] = set()
        if cfg.regime.enabled and not bull and cfg.regime.bear_liquidate:
            act = [b for b in self.active_baskets() if b.status == "active"]
            excess = len(act) - cfg.regime.bear_max_baskets
            if excess > 0:
                for b in sorted(act, key=lambda x: x.ret(price))[:excess]:
                    forced.add(b.id)

        # 1) 기존 바스켓: 청산 판단 → MOC / 로트 매도 LOC / 슬라이스 매수 LOC
        for b in self.active_baskets():
            reason = "regime_bear" if b.id in forced else self.exit_reason(b, idx, price)
            if reason is not None:
                if reason in ("basket_sl", "regime_bear"):
                    self._last_sl_idx = idx
                if b.lots:
                    b.status = "liquidating"
                    b.close_reason = reason
                    orders.append(Order(b.id, "SELL", "MOC", b.shares(), None, reason))
                else:
                    returned += self.close_basket(b, date, idx, reason)
                continue

            # 로트별 익절 LOC (같은 지정가끼리 묶음)
            tp = self.lot_tp_pct(vol)
            groups: dict[float, list[Lot]] = {}
            for l in b.lots:
                if l.tp_done:
                    continue
                lim = round(l.cost * (1.0 + tp), 4)
                groups.setdefault(lim, []).append(l)
            frac = cfg.exit.lot_tp_sell_frac
            for lim, ls in sorted(groups.items()):
                orders.append(Order(b.id, "SELL", "LOC", sum(l.qty for l in ls) * frac, lim, "lot_tp",
                                    lot_costs=tuple(l.cost for l in ls)))

            # 슬라이스 매수 LOC
            if cfg.regime.enabled and not bull and cfg.regime.bear_no_new_lots:
                continue
            slice_val = b.budget / cfg.baskets.slices
            mult = self.slice_mult(b, price, bull)
            avail = b.cash_avail()
            amt = min(slice_val * mult, avail)
            if amt < slice_val * 0.25:   # 잔여 현금이 너무 작으면 생략
                continue
            first = not b.lots and b.n_buys == 0
            if first:
                amt = min(slice_val * mult * cfg.entry.first_slice_mult, avail)
            dip = self.dip_pct(vol, first)
            lim = round(price * (1.0 - dip), 4)
            if lim <= 0:
                continue
            orders.append(Order(b.id, "BUY", "LOC", amt / lim, lim, "first_slice" if first else "dip_slice"))

        # 2) 신규 바스켓 오픈 (오픈 즉시 첫 슬라이스 주문)
        idle_cash += returned
        nb = self.maybe_open_basket(idx, date, equity, idle_cash, bull, vol)
        if nb is not None:
            if not (cfg.regime.enabled and not bull and cfg.regime.bear_no_new_lots):
                slice_val = nb.budget / cfg.baskets.slices
                mult = self.slice_mult(nb, price, bull) * cfg.entry.first_slice_mult
                dip = self.dip_pct(vol, True)
                lim = round(price * (1.0 - dip), 4)
                orders.append(Order(nb.id, "BUY", "LOC", min(slice_val * mult, nb.cash_avail()) / lim, lim,
                                    "first_slice"))
        return orders, returned
