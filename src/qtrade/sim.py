"""범용 일간 포지션 시뮬레이터 — 단일 종목, 종가 체결(LOC/MOC), 현금 파킹.

바스켓 전략(engine.py)이 로트·바스켓 상태를 직접 다루는 것과 달리, 여기서는 전략이 매일
"다음 거래일 주문 리스트"만 내고 시뮬레이터가 체결·현금·자산을 관리한다. 상시 보유·국면 스위치 등 포지션형 전략용.

전략 인터페이스 (strategies/base.py 참조):
    prepare(frame) -> frame          지표 컬럼 추가 (미래참조 금지)
    orders(i, frame, state) -> list[Order]   i일 종가 후 다음 거래일 종가 주문
state: SimState(cash, shares, avg_cost, equity, peak, ...)
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .data import TRADING_DAYS
from .engine import BacktestResult, cash_yield_daily
from .strategy import Order


@dataclass
class SimState:
    cash: float
    shares: float = 0.0
    avg_cost: float = 0.0
    equity: float = 0.0
    peak: float = 0.0
    entry_idx: int | None = None
    entry_price: float = 0.0
    high_since_entry: float = 0.0
    extra: dict = field(default_factory=dict)


def run_sim(cfg, strategy, data: pd.DataFrame) -> BacktestResult:
    """cfg: 공통 필드(initial_capital, cash_yield_*, costs, data)를 가진 설정. strategy: prepare/orders 구현체."""
    df = strategy.prepare(data.copy())
    idx = df.index
    close = df["close"].values.astype(float)
    i0 = int(np.argmax(df["ready"].values)) if "ready" in df else 1
    if cfg.data.start:
        i0 = max(i0, int(idx.searchsorted(pd.Timestamp(cfg.data.start))))
    comm, slip = cfg.costs.commission_pct, cfg.costs.slippage_pct
    int_shares = cfg.costs.integer_shares
    dy = cash_yield_daily(cfg, idx)
    st = SimState(cash=float(cfg.initial_capital)); st.peak = st.cash
    pending: list[Order] = []
    trades, rows = [], []
    for i in range(i0, len(df)):
        date, px = idx[i], close[i]
        # 1) 체결
        for o in pending:
            if o.kind == "LOC" and ((o.side == "BUY" and px > o.limit) or (o.side == "SELL" and px < o.limit)):
                continue
            fill = px * (1 + slip) if o.side == "BUY" else px * (1 - slip)
            if o.side == "BUY":
                qty = min(o.qty, st.cash / (fill * (1 + comm)))
                if int_shares: qty = float(np.floor(qty + 1e-9))
                if qty <= 1e-9: continue
                fee = qty * fill * comm
                st.avg_cost = (st.shares * st.avg_cost + qty * fill) / (st.shares + qty)
                st.shares += qty; st.cash -= qty * fill + fee
                if st.entry_idx is None: st.entry_idx, st.entry_price, st.high_since_entry = i, fill, px
                trades.append(dict(date=date, basket=0, side="BUY", kind=o.kind, qty=qty, price=fill, value=qty * fill, fee=fee, pnl=np.nan, reason=o.reason, lots=None))
            else:
                qty = min(o.qty, st.shares)
                if int_shares: qty = float(np.floor(qty + 1e-9))
                if qty <= 1e-9: continue
                fee = qty * fill * comm
                pnl = qty * (fill - st.avg_cost) - fee
                lots = [(qty, st.avg_cost, idx[st.entry_idx] if st.entry_idx is not None else date)]
                st.shares -= qty; st.cash += qty * fill - fee
                if st.shares <= 1e-9: st.shares, st.avg_cost, st.entry_idx = 0.0, 0.0, None
                trades.append(dict(date=date, basket=0, side="SELL", kind=o.kind, qty=qty, price=fill, value=qty * fill, fee=fee, pnl=pnl, reason=o.reason, lots=lots))
        pending = []
        # 2) 이자
        interest = st.cash * dy[i] * cfg.cash_yield_fraction if dy[i] else 0.0
        st.cash += interest
        # 3) 평가
        invested = st.shares * px
        st.equity = st.cash + invested; st.peak = max(st.peak, st.equity)
        if st.shares > 0: st.high_since_entry = max(st.high_since_entry, px)
        rows.append(dict(date=date, close=px, ref_close=df["ref_close"].iat[i] if "ref_close" in df else px,
                         vol=df["vol"].iat[i] if "vol" in df else np.nan, bull=bool(df["bull"].iat[i]) if "bull" in df else True,
                         halted=False, interest=interest, cash=st.cash, invested=invested, equity=st.equity,
                         n_active=int(st.shares > 0), exposure=invested / st.equity if st.equity > 0 else 0.0))
        # 4) 다음 날 주문
        pending = strategy.orders(i, df, st)
    frame = pd.DataFrame(rows).set_index("date")
    trades_df = pd.DataFrame(trades) if trades else pd.DataFrame(columns=["date", "basket", "side", "kind", "qty", "price", "value", "fee", "pnl", "reason", "lots"])
    baskets_df = pd.DataFrame(columns=["id", "opened", "closed", "status", "budget", "pnl", "ret", "n_buys", "n_sells", "hold_days", "reason"])
    return BacktestResult(cfg=cfg, equity=frame["equity"].rename("equity"), frame=frame, trades=trades_df, baskets=baskets_df,
                          pending_orders=pending, strategy=None, final_cash=st.cash)
