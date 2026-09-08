"""일간 백테스트 엔진: LOC/MOC 종가 체결 시뮬레이션."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

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
    n_skipped_orders: int = 0          # 정수 주 제약으로 건너뛴 주문 수 (integer_shares=True 일 때)
    n_fillable_orders: int = 0         # 가격 조건을 만족해 체결 대상이 된 주문 수


def prepare_frame(cfg: StrategyConfig, data: pd.DataFrame | None = None) -> pd.DataFrame:
    df = (data if data is not None else build_dataset(cfg.data)).copy()
    df["vol"] = realized_vol(df["close"], cfg.entry.vol_window)
    ma = sma(df["ref_close"], cfg.regime.ma_window)
    df["bull"] = regime_flags(df["ref_close"], ma, cfg.regime.ma_band)
    df["sym_sma"] = sma(df["close"], cfg.regime.breaker_resume_sma)
    return df


def regime_flags(ref: pd.Series, ma: pd.Series, band: float) -> pd.Series:
    """히스테리시스 밴드가 있는 강세/약세 플래그. MA 미산출 구간은 NaN."""
    if band <= 0:
        return (ref > ma).where(ma.notna(), other=np.nan)
    out = np.full(len(ref), np.nan)
    state = None
    r, m = ref.values, ma.values
    for i in range(len(r)):
        if np.isnan(m[i]):
            continue
        if state is None:
            state = r[i] > m[i]
        elif state and r[i] < m[i] * (1 - band):
            state = False
        elif not state and r[i] > m[i] * (1 + band):
            state = True
        out[i] = state
    return pd.Series(out, index=ref.index)


def cash_yield_daily(cfg: StrategyConfig, idx: pd.DatetimeIndex, bundled_dir: str | None = None) -> np.ndarray:
    """일별 현금 수익률(스프레드 반영). 숫자면 고정, 'TBILL3M' 이면 번들 연평균 표."""
    y = cfg.cash_yield_annual
    if isinstance(y, str):
        path = Path(bundled_dir or cfg.data.bundled_dir) / f"{y}_annual.csv"
        tbl = pd.read_csv(path).set_index("year")["rate"]
        years = pd.Index(idx.year)
        rates = years.map(lambda yy: float(tbl.get(yy, tbl.iloc[-1] if yy > tbl.index.max() else tbl.iloc[0]))).to_numpy(dtype=float)
    else:
        rates = np.full(len(idx), float(y))
    rates = np.maximum(rates + cfg.cash_yield_spread, 0.0)
    return rates / TRADING_DAYS


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
    int_shares = cfg.costs.integer_shares
    n_skipped = 0
    n_fillable = 0
    daily_yield_arr = cash_yield_daily(cfg, idx)

    pending: list[Order] = []
    trades: list[dict] = []
    breaker = cfg.regime.breaker_dd
    halted = False
    rk = cfg.risk
    risk_peak = float(cfg.initial_capital)
    bk_peak = float(cfg.initial_capital)
    sym_sma = df["sym_sma"].values.astype(float)
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
                n_fillable += 1
                qty = min(o.qty, max(b.cash_avail(), 0.0) / (fill_px * (1 + comm)))
                qty = min(qty, cash / (fill_px * (1 + comm)))
                if int_shares:
                    qty = float(np.floor(qty + 1e-9))
                if qty <= 1e-9:
                    n_skipped += 1
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
                elif o.reason == "upday_sell":
                    lots = list(b.lots)
                    sh = sum(l.qty for l in lots)
                    frac = min(o.qty / sh, 1.0) if sh > 0 else 0.0
                else:
                    lots = [l for l in b.lots if l.cost in o.lot_costs and not l.tp_done]
                    frac = cfg.exit.lot_tp_sell_frac
                if not lots or frac <= 0:
                    continue
                n_fillable += 1
                if int_shares and frac < 1.0:
                    whole = float(np.floor(sum(l.qty for l in lots) * frac + 1e-9))
                    if whole <= 0:
                        n_skipped += 1
                        continue
                    frac = whole / sum(l.qty for l in lots)
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
                        if o.reason == "lot_tp":
                            l.tp_done = True
                        if l.qty < 1e-9:
                            b.lots.remove(l)
                trades.append(dict(date=date, basket=b.id, side="SELL", kind=o.kind, qty=qty, price=fill_px,
                                   value=qty * fill_px, fee=fee, pnl=proceeds - cost, reason=o.reason))
        pending = []

        # ---- 2) MOC 청산 완료 바스켓 닫기 ----
        for b in strat.active_baskets():
            if b.status == "liquidating" and not b.lots:
                strat.close_basket(b, date, i, b.close_reason or "liquidated")

        # ---- 3) 현금 이자 (파킹 비율만큼) ----
        if daily_yield_arr[i]:
            cash *= 1 + daily_yield_arr[i] * cfg.cash_yield_fraction

        # ---- 4) 평가 ----
        invested = sum(b.market_value(px) for b in strat.active_baskets())
        equity = cash + invested
        idle_cash = cash - strat.reserved_cash()
        n_active = len(strat.active_baskets())
        bull = bool(bull_arr[i])
        if breaker:
            if not halted:
                bk_peak = max(bk_peak, equity)
                if equity <= bk_peak * (1.0 - breaker):
                    halted = True
            elif not np.isnan(sym_sma[i]) and px > sym_sma[i]:
                halted = False
                bk_peak = equity
            if halted:
                bull = False
        # ---- 노출 상한(변동성 타게팅) / 낙폭 연동 축소 ----
        exposure_cap = rk.max_exposure
        if rk.vol_target_annual and vol[i] == vol[i] and vol[i] > 0:
            exposure_cap = min(exposure_cap, rk.vol_target_annual / (vol[i] * np.sqrt(TRADING_DAYS)))
        size_mult = 1.0
        risk_peak = max(risk_peak, equity)
        if rk.dd_scale_start is not None:
            dd_now = 1.0 - equity / risk_peak
            if dd_now > rk.dd_scale_start:
                t = min(1.0, (dd_now - rk.dd_scale_start) / max(rk.dd_scale_floor - rk.dd_scale_start, 1e-9))
                size_mult = 1.0 - (1.0 - rk.dd_scale_min_mult) * t
        rows.append(dict(date=date, close=px, ref_close=df["ref_close"].iat[i], vol=vol[i], bull=bull, halted=halted,
                         exposure_cap=exposure_cap, size_mult=size_mult,
                         cash=cash, invested=invested, equity=equity, n_active=n_active,
                         exposure=invested / equity if equity > 0 else 0.0))

        # ---- 5) 내일 주문 생성 ----
        pending, returned = strat.generate_orders(i, date, px, vol[i], bull, equity, idle_cash, halt=halted,
                                                  exposure_cap=exposure_cap, size_mult=size_mult, invested=invested)

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
                          pending_orders=pending, strategy=strat, final_cash=cash,
                          n_skipped_orders=n_skipped, n_fillable_orders=n_fillable)
