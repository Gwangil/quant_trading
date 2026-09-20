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


def aggregate_orders(pending) -> list:
    """같은 (side, kind, 지정가) 주문을 한 건으로 합친다 — 집행기 주문 건수 절감. 반환: (side, kind, limit, qty, reasons, basket_ids)."""
    groups: dict = {}
    for o in pending:
        key = (o.side, o.kind, None if o.limit is None else round(float(o.limit), 2))
        g = groups.setdefault(key, {"qty": 0.0, "reasons": [], "baskets": []})
        g["qty"] += o.qty
        if o.reason not in g["reasons"]: g["reasons"].append(o.reason)
        if o.basket_id not in g["baskets"]: g["baskets"].append(o.basket_id)
    out = []
    for (side, kind, lim), g in groups.items():
        out.append((side, kind, lim, g["qty"], g["reasons"], g["baskets"]))
    # 매도 먼저(현금 확보), 그다음 매수; 같은 쪽은 가격순
    out.sort(key=lambda x: (0 if x[0] == "SELL" else 1, x[2] if x[2] is not None else -1))
    return out


def build_sheet(res: BacktestResult, env: str = "paper", strategy_name: str | None = None,
                inception: str | None = None, exchange: str | None = None) -> dict:
    cfg = res.cfg
    f = res.frame
    sym = cfg.data.symbol
    last = f.index[-1]
    px = float(f["close"].iloc[-1])
    orders = []
    for side, kind, lim, q, reasons, baskets in aggregate_orders(res.pending_orders):
        qty = int(q)
        if qty <= 0:
            continue
        orders.append({
            "side": side, "symbol": sym, "qty": qty,
            "ref_price": round(lim if lim is not None else px, 2),
            "ord_type": kind, "reason": "+".join(reasons), "tag": "basket-" + ",".join(str(b) for b in baskets),
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


# ---------------- Meritz (rpa_claude) orders.csv ----------------
MERITZ_COLUMNS = ["side", "symbol", "quantity", "price", "order_type", "memo"]


def build_meritz_rows(res: BacktestResult) -> list[dict]:
    """rpa_claude `orders/orders.csv` 규격: side(buy/sell), symbol, quantity(정수), price, order_type(LOC/MOC/보통), memo.
    MOC 는 needs_price=false 라 price 를 비운다."""
    sym = res.cfg.data.symbol
    rows = []
    for side, kind, lim, q, reasons, baskets in aggregate_orders(res.pending_orders):
        qty = int(q)
        if qty <= 0:
            continue
        is_moc = kind == "MOC"
        rows.append({"side": side.lower(), "symbol": sym, "quantity": qty,
                     "price": "" if is_moc else f"{lim:.2f}",
                     "order_type": "MOC" if is_moc else "LOC",
                     "memo": f"{res.cfg.name}:{'+'.join(reasons)}:basket-{','.join(str(b) for b in baskets)}"})
    return rows


def meritz_csv_text(rows: list[dict]) -> str:
    import csv, io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=MERITZ_COLUMNS, lineterminator="\n")
    w.writeheader(); w.writerows(rows)
    return buf.getvalue()


def save_meritz_csv(res: BacktestResult, out_dir: str | Path, name: str | None = None) -> Path:
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    trade_date = str(res.frame.index[-1].date())
    path = out / (name or f"orders_meritz_{res.cfg.data.symbol}_{res.cfg.name}_{trade_date}.csv")
    path.write_text(meritz_csv_text(build_meritz_rows(res)), encoding="utf-8")
    return path
