"""auto_trade 주문서(Order Sheet) 규격 v1 로 내보내기.

규격: Gwangil/auto_trade docs/order-sheet-spec.md
- meta.env 는 집행 환경과 일치해야 하며, 모의투자(paper)는 지정가(limit)만 지원 → LOC/MOC 는 집행기가 limit 로 대체.
- qty 는 양의 정수. ref_price 는 지정가(USD, 소수 2자리). MOC 는 KIS 가 단가 0 으로 보내므로 ref_price 에는 참고가(종가)를 둔다.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .engine import BacktestResult

EXCHANGES = {"SOXL": "AMEX", "TQQQ": "NASD", "TECL": "AMEX", "SOXX": "NASD"}


def build_sheet(res: BacktestResult, env: str = "paper", strategy_name: str | None = None,
                inception: str | None = None, exchange: str | None = None) -> dict:
    cfg = res.cfg
    f = res.frame
    sym = cfg.data.symbol
    last = f.index[-1]
    px = float(f["close"].iloc[-1])
    orders = []
    for o in res.pending_orders:
        qty = int(o.qty)
        if qty <= 0:
            continue
        orders.append({
            "side": o.side, "symbol": sym, "qty": qty,
            "ref_price": round(float(o.limit) if o.limit is not None else px, 2),
            "ord_type": o.kind, "reason": o.reason, "tag": f"basket-{o.basket_id}",
        })
    positions = []
    for b in res.strategy.active_baskets():
        positions.append({"id": b.id, "active": True, "shares": round(b.shares(), 4),
                          "avg_cost": round(b.avg_cost(), 4) if b.avg_cost() else 0.0,
                          "cash": round(b.cash_avail(), 2), "pnl_pct": round(b.ret(px) * 100, 2),
                          "held_days": int(len(f) - 1 - f.index.get_loc(b.opened)) if b.opened in f.index else 0})
    halted = bool(f["halted"].iloc[-1]) if "halted" in f else False
    return {
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "env": env,
            "strategy": strategy_name or cfg.name,
            "strategy_kind": "qtrade_basket_loc",
            "symbol": sym,
            "exchange": exchange or EXCHANGES.get(sym, "AMEX"),
            "inception": inception or (cfg.data.start or str(f.index[0].date())),
            "trade_date": str(last.date()),
            "close": round(px, 4),
            "equity": round(float(res.equity.iloc[-1]), 2),
            "capital": float(cfg.initial_capital),
            "state": {"halted": halted, "bull": bool(f["bull"].iloc[-1]), "n_active": int(f["n_active"].iloc[-1]),
                      "cash": round(res.final_cash, 2)},
        },
        "orders": orders,
        "positions": positions,
    }


def save_sheet(sheet: dict, out_dir: str | Path) -> Path:
    m = sheet["meta"]
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    path = out / f"orders_{m['env']}_{m['symbol']}_{m['strategy']}_{m['trade_date']}.json"
    path.write_text(json.dumps(sheet, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
