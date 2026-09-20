"""데이터 갱신(splice/sanitize), 현금 파킹 수익률, 주문서 JSON 내보내기."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from qtrade.updater import splice, sanitize_daily, staleness_days
from qtrade.engine import run_backtest, cash_yield_daily
from qtrade.sheet import build_sheet, save_sheet
from tests.test_core import make_data, base_cfg


def test_splice_scales_bundled_segment_to_fresh():
    idx = pd.bdate_range("2020-01-01", periods=10)
    bundled = pd.DataFrame({"Close": np.linspace(10, 19, 10)}, index=idx)
    fresh = pd.DataFrame({"Close": np.linspace(38, 48, 6)}, index=idx[4:])   # 번들의 2배 수준으로 시작
    out = splice(bundled, fresh)
    assert len(out) == 10
    assert out.loc[idx[3], "Close"] == pytest.approx(13 * 38 / 14)            # 스케일 = 38/14
    assert (out.loc[idx[4]:, "Close"].values == fresh["Close"].values).all()
    assert out.index.is_monotonic_increasing and not out.index.duplicated().any()


def test_sanitize_drops_incomplete_and_invalid_bars():
    idx = pd.bdate_range("2026-09-01", periods=5)
    df = pd.DataFrame({"Open": [10, 10, 10, 10, 10], "High": [11, 9, 11, 11, 11], "Low": [9, 9, 9, 9, 9],
                       "Close": [10.5] * 5, "Volume": [1] * 5}, index=idx)
    now = datetime(2026, 9, 4, 12, 0, tzinfo=ZoneInfo("America/New_York"))   # 9/4 장중 → 9/4 봉 미완성
    out = sanitize_daily(df, "X", now_et=now)
    assert idx[4] not in out.index and idx[3] not in out.index   # 9/4(미완성), 9/7 은 원래 없음 → 마지막은 9/3
    assert idx[1] not in out.index                                 # High < Open 위반
    assert staleness_days(out.index[-1], now) == 0


def test_cash_yield_series_and_fraction():
    cfg = base_cfg(**{"cash_yield_annual": "TBILL3M", "cash_yield_fraction": 0.5, "cash_yield_spread": -0.001})
    idx = pd.bdate_range("2023-01-02", periods=5)
    d = cash_yield_daily(cfg, idx, bundled_dir="data/bundled")
    assert d[0] == pytest.approx((0.0507 - 0.001) / 252)
    # 파킹 비율이 반영되어 현금이 불어난다 (매매 없는 구간에서 비교)
    data = make_data(seed=11)
    a = run_backtest(base_cfg(**{"cash_yield_annual": 0.04}), data).equity
    b = run_backtest(base_cfg(**{"cash_yield_annual": 0.04, "cash_yield_fraction": 0.5}), data).equity
    c = run_backtest(base_cfg(), data).equity
    assert a.iloc[-1] > b.iloc[-1] > c.iloc[-1]


def test_order_sheet_matches_auto_trade_spec(tmp_path):
    data = make_data(seed=2)
    res = run_backtest(base_cfg(**{"data.symbol": "SOXL"}), data)
    sheet = build_sheet(res, env="paper")
    for k in ("env", "symbol", "trade_date", "strategy", "close", "equity", "capital", "state"):
        assert k in sheet["meta"]
    assert sheet["meta"]["env"] == "paper"
    for o in sheet["orders"]:
        assert o["side"] in ("BUY", "SELL") and isinstance(o["qty"], int) and o["qty"] > 0
        assert o["ord_type"] in ("LOC", "MOC") and isinstance(o["ref_price"], float)
        assert o["symbol"] == "SOXL"
    path = save_sheet(sheet, tmp_path)
    assert path.name.startswith("orders_paper_SOXL_") and json.loads(path.read_text(encoding="utf-8"))["meta"]["symbol"] == "SOXL"


def test_meritz_csv_rows_follow_rpa_claude_spec():
    from qtrade.sheet import build_meritz_rows, meritz_csv_text, MERITZ_COLUMNS
    data = make_data(seed=2)
    res = run_backtest(base_cfg(**{"data.symbol": "SOXL", "exit.max_hold_days": 10, "exit.hard_max_hold_days": 12}), data)
    rows = build_meritz_rows(res)
    assert rows, "pending orders expected"
    for r in rows:
        assert r["side"] in ("buy", "sell") and r["symbol"] == "SOXL" and r["quantity"] > 0
        assert r["order_type"] in ("LOC", "MOC")
        assert (r["price"] == "") == (r["order_type"] == "MOC")
    text = meritz_csv_text(rows)
    assert text.splitlines()[0] == ",".join(MERITZ_COLUMNS)


def test_serve_endpoints(tmp_path):
    import threading, urllib.request, json as _json
    from http.server import ThreadingHTTPServer
    from qtrade.serve import OrderService, make_handler
    from qtrade.config import save_config
    cfg = base_cfg(**{"data.symbol": "SOXL", "data.reference": "SOXX", "data.source": "csv", "data.cache_dir": "data/cache"})
    (tmp_path / "configs").mkdir(); save_config(cfg, tmp_path / "configs" / "soxl_t.yaml")
    svc = OrderService(configs_dir=tmp_path / "configs", out_dir=tmp_path / "out")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(svc, "s3cret"))
    th = threading.Thread(target=httpd.serve_forever, daemon=True); th.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        with pytest.raises(urllib.error.HTTPError) as ei:
            urllib.request.urlopen(f"{base}/health?profile=t")
        assert ei.value.code == 401
        h = _json.loads(urllib.request.urlopen(urllib.request.Request(f"{base}/health?profile=t", headers={"X-Token": "s3cret"})).read())
        assert h["ok"] and "last_close" in h
        r = urllib.request.urlopen(f"{base}/orders?profile=t&format=meritz&token=s3cret")
        assert r.headers["Content-Type"].startswith("text/csv") and r.read().decode().startswith("side,symbol")
        k = _json.loads(urllib.request.urlopen(f"{base}/orders?profile=t&format=kis&env=paper&token=s3cret").read())
        assert k["meta"]["env"] == "paper" and k["meta"]["symbol"] == "SOXL"
        assert list((tmp_path / "out").glob("orders_*"))
    finally:
        httpd.shutdown()
