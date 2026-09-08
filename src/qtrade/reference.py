"""기준 전략(invest_strategy baseline / v5) 재구현 — 비교용.

원본: Gwangil/invest_strategy `strategy_backtest.py`(pm님 baseline) + `engine.py`(계좌 서킷브레이커).
규칙(당일 종가 체결, 정수 주, 바구니 예산 고정 = 단리):
  진입: 빈 바구니 있음 & 전일 RSI(14) < rsi_max & 당일 등락률 ≤ max_entry_rise → 예산 × buy_ratio 매수 (하루 1개)
  관리(우선순위): 보유 ≥ max_hold_days → 전량 / 상승일 & 수익률 < target → partial 매도 / 수익률 ≥ target → 전량 /
                 잔여현금 > 100 & 수익률 ≤ addon_drop → 예산 × buy_ratio 추가매수
  서킷브레이커(v5): 전일 자산 ≤ 고점 × (1 + breaker_dd) → 당일 전량 청산·중단, 전일 종가 > SMA(resume_sma) 면 재개(고점 리셋)
동등성은 tests/test_reference.py 에서 원본 실행 결과와 대조한다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class ReferenceParams:
    div_count: int = 8
    buy_ratio: float = 0.6
    partial_sell: float = 0.2
    target_profit: float = 0.005      # baseline 0.5%, v5 1.5%
    rsi_max: float = 90
    rsi_period: int = 14
    max_hold_days: int = 40           # 달력일 기준 (원본과 동일)
    max_entry_rise: float = -0.001
    addon_drop: float = -0.05
    commission: float = 0.001
    breaker_dd: float | None = None   # v5: -0.15
    resume_sma: int = 200
    compound: bool = False            # True: 바구니 (재)시작 시 예산 = 현재 총자산 / div_count (복리 비교용, 원본에는 없음)


BASELINE = ReferenceParams()
V5 = ReferenceParams(target_profit=0.015, breaker_dd=-0.15)


def rsi_sma(close: pd.Series, period: int) -> pd.Series:
    d = close.diff()
    gain = d.where(d > 0, 0).rolling(period).mean()
    loss = (-d.where(d < 0, 0)).rolling(period).mean()
    return 100 - 100 / (1 + gain / loss)


@dataclass
class _Div:
    alloc: float
    cash: float
    shares: int = 0
    avg: float = 0.0
    active: bool = False
    start: pd.Timestamp | None = None
    cycle_cash: float = 0.0
    trades: list = field(default_factory=list)

    def buy(self, px, amount, date, comm):
        if not self.active:
            self.cycle_cash = self.cash
            self.start = None
        n = int(math.floor(min(amount, self.cash) / (px * (1 + comm))))
        if n <= 0:
            return
        val = n * px
        self.avg = (self.shares * self.avg + val) / (self.shares + n)
        self.shares += n
        self.cash -= val * (1 + comm)
        self.active = True
        if self.start is None:
            self.start = date
        self.trades.append(("BUY", date, px, n))

    def sell(self, px, pct, date, comm):
        n = math.floor(self.shares * pct)
        self.shares -= n
        self.cash += n * px * (1 - comm)
        self.trades.append(("SELL", date, px, n))
        if self.shares < 1e-6:
            pnl = self.cash - self.cycle_cash
            self.active, self.shares, self.avg = False, 0, 0.0
            self.cash = self.alloc
            return pnl
        return None


def run_reference(close: pd.Series, capital: float, p: ReferenceParams = BASELINE,
                  rsi: pd.Series | None = None) -> tuple[pd.Series, int, int]:
    """(일별 총자산, 종료 바구니 수, 체결 건수) 반환. rsi 를 주면(스냅샷 컬럼) 그대로 쓰고, 없으면 close 로 계산."""
    close = close.dropna()
    rsi = rsi.reindex(close.index) if rsi is not None else rsi_sma(close, p.rsi_period)
    df = pd.DataFrame({"c": close, "prev_c": close.shift(1), "prev_rsi": rsi.shift(1)})
    if p.breaker_dd is not None:
        df["prev_bull"] = (close > close.rolling(p.resume_sma).mean()).shift(1)
    df = df.dropna(subset=["prev_rsi"])   # 원본: RSI(및 dropna 된 첫 행) 이후부터 매매
    alloc = capital / p.div_count
    divs = [_Div(alloc, alloc) for _ in range(p.div_count)]
    realized = 0.0
    n_closed = 0
    halted, peak, prev_eq = False, capital, capital
    eq = []

    def record(date, px):
        nonlocal prev_eq
        total = sum(d.cash + d.shares * px for d in divs) + realized
        eq.append((date, total)); prev_eq = total

    def sell(d, px, pct, date):
        nonlocal realized, n_closed
        pnl = d.sell(px, pct, date, p.commission)
        if pnl is not None:
            realized += pnl; n_closed += 1

    for date, r in df.iterrows():
        px, prev = r["c"], r["prev_c"]
        if p.breaker_dd is not None:
            peak = max(peak, prev_eq)
            dd = prev_eq / peak - 1
            if not halted and dd <= p.breaker_dd:
                halted = True
                for d in divs:
                    if d.active:
                        sell(d, px, 1.0, date)
                record(date, px); continue
            if halted:
                bull = bool(r["prev_bull"]) if not pd.isna(r["prev_bull"]) else False
                if bull:
                    halted = False; peak = prev_eq
                else:
                    record(date, px); continue
        for d in divs:
            if not d.active:
                continue
            profit = (px - d.avg) / d.avg if d.avg else 0.0
            if (date - d.start).days >= p.max_hold_days:
                sell(d, px, 1.0, date); continue
            if px > prev and d.avg > 0 and profit < p.target_profit:
                sell(d, px, p.partial_sell, date)
            elif profit >= p.target_profit:
                sell(d, px, 1.0, date)
            elif d.cash > 100 and profit <= p.addon_drop:
                d.buy(px, d.alloc * p.buy_ratio, date, p.commission)
        if r["prev_rsi"] < p.rsi_max:
            chg = (px - prev) / prev if prev > 0 else 0
            if chg <= p.max_entry_rise and sum(d.active for d in divs) < p.div_count:
                for d in divs:
                    if not d.active:
                        a = (prev_eq / p.div_count) if p.compound else alloc
                        realized += d.cash - a          # 예산 변경분은 계좌 실현손익 계정으로 이동 (총자산 불변)
                        d.alloc = a; d.cash = a
                        d.buy(px, a * p.buy_ratio, date, p.commission)
                        break
        record(date, px)
    s = pd.Series(dict(eq), name="equity")
    s.index = pd.DatetimeIndex(s.index)
    n_fills = sum(len(d.trades) for d in divs)
    return s, n_closed, n_fills
