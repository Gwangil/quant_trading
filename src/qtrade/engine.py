"""일간 백테스트 엔진: LOC/MOC 종가 체결 시뮬레이션."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import StrategyConfig
from .data import build_dataset, TRADING_DAYS
from .indicators import realized_vol, sma
from .strategy import BasketStrategy, Basket, Lot, Order


@dataclass
class BacktestResult:
    cfg: StrategyConfig
    equity: pd.Series                  # 일별 총자산
    frame: pd.DataFrame                # close, ref_close, vol, bull, cash, invested, n_active
    trades: pd.DataFrame               # 체결 내역
    baskets: pd.DataFrame              # 바스켓 라운드 내역
    pending_orders: list[Order] = field(default_factory=list)   # 마지막 날 기준 다음 거래일 주문
    strategy: BasketStrategy | None = None
    final_cash: float = 0.0


def prepare_frame(cfg: StrategyConfig, data: pd.DataFrame | None = None) -> pd.DataFrame:
    df = (data if data is not None else build_dataset(cfg.data)).copy()
    df["vol"] = realized_vol(df["close"], cfg.entry.vol_window)
    ma = sma(df["ref_close"], cfg.regime.ma_window)
    df["bull"] = (df["ref_close"] > ma).where(ma.notna(), other=np.nan)
    return df


def _trading_start_index(cfg: StrategyConfig, df: pd.DataFrame) -> int:
    valid = df["vol"].notna() & df["bull"].notna()
    if not valid.any():
        raise ValueError("데이터가 지표 계산 창보다 짧습니다")
    i0 = int(np.argmax(valid.values))
    if cfg.data.start:
        s = pd.Timestamp(cfg.data.start)
        j = int(df.index.searchsorted(s))
        i0 = max(i0, j)
    return max(i0, 1)


def run_backtest(cfg: StrategyConfig, data: pd.DataFrame | None = None) -> BacktestResult:
    df = prepare_frame(cfg, data)
    i0 = _trading_start_index(cfg, df)
    idx = df.index
    close = df["close"].values.astype(float)
    vol = df["vol"].values.astype(float)
    bull_arr = df["bull"].fillna(False).astype(bool).values

    strat = BasketStrategy(cfg)
    cash = float(cfg.initial_capital)     # 포트폴리오 전체 현금 (바스켓 예약분 포함)
    comm = cfg.costs.commission_pct
    slip = cfg.costs.slippage_pct
    daily_yield = cfg.cash_yield_annual / TRADING_DAYS

    pending: list[Order] = []
    trades: list[dict] = []
    peak_equity = float(cfg.initial_capital)
    brake_until = -1            # 브레이크 해제 인덱스
    brake_low = float("inf")    # 브레이크 발동 시점 자산 (재발동은 새 저점에서만)
    brake = cfg.regime.portfolio_dd_brake if cfg.regime.enabled else None
    rows: list[dict] = []
    baskets_by_id: dict[int, Basket] = {}

    def basket(bid: int) -> Basket:
        if bid not in baskets_by_id:
            baskets_by_id.update({b.id: b for b in strat.baskets})
        return baskets_by_id[bid]

    n = len(df)
    for i in range(i0, n):
        date = idx[i]
        px = close[i]

        # ---- 1) 전일 생성 주문을 오늘 종가에 체결 ----
        for o in pending:
            b = basket(o.basket_id)
            if o.side == "BUY":
                if o.kind == "LOC" and px > o.limit:
                    continue
                fill_px = px * (1 + slip)
                qty = min(o.qty, max(b.cash_avail(), 0.0) / (fill_px * (1 + comm)))
                qty = min(qty, cash / (fill_px * (1 + comm)))
                if qty <= 1e-9:
                    continue
                fee = qty * fill_px * comm
                cash -= qty * fill_px + fee
                b.lots.append(Lot(qty, fill_px, date, b.id))
                b.realized -= fee
                b.n_buys += 1
                trades.append(dict(date=date, basket=b.id, side="BUY", kind=o.kind, qty=qty, price=fill_px,
                                   value=qty * fill_px, fee=fee, pnl=np.nan, reason=o.reason))
            else:  # SELL
                if o.kind == "LOC" and px < o.limit:
                    continue
                fill_px = px * (1 - slip)
                if o.kind == "MOC":
                    lots = list(b.lots)
                    frac = 1.0
                else:
                    lots = [l for l in b.lots if l.cost in o.lot_costs and not l.tp_done]
                    frac = cfg.exit.lot_tp_sell_frac
                if not lots:
                    continue
                qty = sum(l.qty for l in lots) * frac
                cost = sum(l.qty * l.cost for l in lots) * frac
                fee = qty * fill_px * comm
                proceeds = qty * fill_px - fee
                cash += proceeds
                b.realized += proceeds - cost
                b.n_sells += 1
                for l in lots:
                    if frac >= 1.0:
                        b.lots.remove(l)
                    else:
                        l.qty *= (1.0 - frac)
                        l.tp_done = True
                trades.append(dict(date=date, basket=b.id, side="SELL", kind=o.kind, qty=qty, price=fill_px,
                                   value=qty * fill_px, fee=fee, pnl=proceeds - cost, reason=o.reason))
        pending = []

        # ---- 2) MOC 청산 완료 바스켓 닫기 ----
        for b in strat.active_baskets():
            if b.status == "liquidating" and not b.lots:
                strat.close_basket(b, date, i, b.close_reason or "liquidated")

        # ---- 3) 현금 이자 ----
        if daily_yield:
            cash *= 1 + daily_yield

        # ---- 4) 평가 ----
        invested = sum(b.market_value(px) for b in strat.active_baskets())
        equity = cash + invested
        idle_cash = cash - strat.reserved_cash()
        n_active = len(strat.active_baskets())
        bull = bool(bull_arr[i])
        if brake:
            if equity > peak_equity:
                peak_equity, brake_low = equity, float("inf")
            dd = equity / peak_equity - 1.0
            if dd <= -brake and i > brake_until and equity < brake_low:
                brake_until = i + cfg.regime.portfolio_dd_brake_days
                brake_low = equity
            if i <= brake_until:
                bull = False
        rows.append(dict(date=date, close=px, ref_close=df["ref_close"].iat[i], vol=vol[i], bull=bull,
                         cash=cash, invested=invested, equity=equity, n_active=n_active,
                         exposure=invested / equity if equity > 0 else 0.0))

        # ---- 5) 내일 주문 생성 ----
        pending, returned = strat.generate_orders(i, date, px, vol[i], bull, equity, idle_cash)

    frame = pd.DataFrame(rows).set_index("date")
    eq = frame["equity"].rename("equity")
    trades_df = pd.DataFrame(trades) if trades else pd.DataFrame(
        columns=["date", "basket", "side", "kind", "qty", "price", "value", "fee", "pnl", "reason"])
    last_px = close[n - 1]
    brows = []
    for b in strat.baskets:
        brows.append(dict(id=b.id, opened=b.opened, closed=b.closed, status=b.status, budget=b.budget,
                          pnl=b.pnl(last_px), ret=b.ret(last_px), n_buys=b.n_buys, n_sells=b.n_sells,
                          hold_days=(b.hold_days_at_close if b.hold_days_at_close is not None
                                     else (n - 1) - b.opened_idx),
                          reason=b.close_reason))
    baskets_df = pd.DataFrame(brows) if brows else pd.DataFrame(
        columns=["id", "opened", "closed", "status", "budget", "pnl", "ret", "n_buys", "n_sells", "hold_days", "reason"])
    return BacktestResult(cfg=cfg, equity=eq, frame=frame, trades=trades_df, baskets=baskets_df,
                          pending_orders=pending, strategy=strat, final_cash=cash)
