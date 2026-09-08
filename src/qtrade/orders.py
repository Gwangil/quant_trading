"""실전용 다음 거래일 LOC/MOC 주문표 생성.

상태 관리 방식: 별도 상태파일 대신 '설정된 시작일·초기자본으로 전 구간을 재현(replay)'한 뒤
마지막 종가 기준으로 생성된 주문을 출력한다. 실제 체결이 시뮬레이션과 달라지면
configs 의 start/initial_capital 을 현재 시점 기준으로 재설정해 새 라운드로 시작하면 된다.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import StrategyConfig
from .engine import run_backtest, BacktestResult


def orders_table(res: BacktestResult, lot_size: int = 1) -> pd.DataFrame:
    sym = res.cfg.data.symbol
    rows = []
    for o in res.pending_orders:
        qty = int(o.qty // lot_size * lot_size) if lot_size > 1 else int(o.qty)
        if qty <= 0:
            continue
        rows.append(dict(symbol=sym, side=o.side, type=o.kind, limit=None if o.limit is None else round(o.limit, 2),
                         qty=qty, basket=o.basket_id, reason=o.reason))
    cols = ["symbol", "side", "type", "limit", "qty", "basket", "reason"]
    return pd.DataFrame(rows, columns=cols)


def state_table(res: BacktestResult) -> pd.DataFrame:
    px = float(res.frame["close"].iloc[-1])
    rows = []
    for b in res.strategy.active_baskets():
        rows.append(dict(basket=b.id, opened=b.opened.date(), hold_days=len(res.frame) - 1 - res.frame.index.get_loc(b.opened)
                         if b.opened in res.frame.index else None,
                         budget=round(b.budget, 2), shares=round(b.shares(), 4),
                         avg_cost=None if b.avg_cost() is None else round(b.avg_cost(), 2),
                         cash_avail=round(b.cash_avail(), 2), pnl=round(b.pnl(px), 2), ret=round(b.ret(px), 4),
                         status=b.status))
    return pd.DataFrame(rows, columns=["basket", "opened", "hold_days", "budget", "shares", "avg_cost",
                                       "cash_avail", "pnl", "ret", "status"])


def generate(cfg: StrategyConfig, out_dir: str | Path | None = None) -> tuple[pd.DataFrame, pd.DataFrame, BacktestResult]:
    res = run_backtest(cfg)
    orders = orders_table(res)
    state = state_table(res)
    if out_dir is not None:
        out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
        tag = res.frame.index[-1].strftime("%Y%m%d")
        orders.to_csv(out / f"orders_{tag}.csv", index=False)
        state.to_csv(out / f"state_{tag}.csv", index=False)
    return orders, state, res


def render(orders: pd.DataFrame, state: pd.DataFrame, res: BacktestResult) -> str:
    f = res.frame
    last = f.index[-1].date()
    halted = bool(f["halted"].iloc[-1]) if "halted" in f else False
    lines = [f"기준일(마지막 종가): {last}  종가 {f['close'].iloc[-1]:.2f}  "
             f"레짐: {'강세' if bool(f['bull'].iloc[-1]) else '약세'}  일변동성 {f['vol'].iloc[-1]:.2%}"
             + ("  ⚠ 서킷브레이커 발동 중(매매 중단)" if halted else ""),
             f"총자산 {res.equity.iloc[-1]:,.2f}  현금 {res.final_cash:,.2f}  활성 바스켓 {int(f['n_active'].iloc[-1])}",
             "", "## 다음 거래일 주문 (종가 주문)",
             orders.to_string(index=False) if len(orders) else "(주문 없음)",
             "", "## 바스켓 현황", state.to_string(index=False) if len(state) else "(활성 바스켓 없음)"]
    return "\n".join(lines)
