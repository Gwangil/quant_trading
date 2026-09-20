"""주문서 발급 서버 (표준 라이브러리 HTTP). 집행기(auto_trade / rpa_claude)가 스케줄 시각에 호출한다.

  qtrade serve --port 8787 --token SECRET [--configs configs] [--out reports/orders] [--update]

엔드포인트 (모두 GET, 헤더 `X-Token: SECRET` 또는 `?token=`):
  /health                          → {"ok": true, "last_close": ..., "stale_days": ...}
  /orders?profile=balanced&format=kis&env=paper   → auto_trade 주문서 JSON
  /orders?profile=balanced&format=meritz          → rpa_claude orders.csv (text/csv)
  /orders?profile=balanced&format=json            → 주문표 + 바스켓 상태 (요약 JSON)
  옵션: &refresh=1 (yfinance 로 시세 갱신 후 생성), &capital=20000&start=2026-10-01 (설정 오버라이드)
발급된 파일은 --out 에도 저장된다. 같은 (profile, 기준일, 오버라이드) 요청은 캐시된다.
LAN 전용을 전제로 한다 — 공개망에 노출하지 말 것.
"""
from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from .config import load_config
from .engine import run_backtest
from .orders import orders_table, state_table
from .sheet import build_sheet, save_sheet, build_meritz_rows, meritz_csv_text, save_meritz_csv
from .updater import update_symbol, staleness_days

logger = logging.getLogger(__name__)


class OrderService:
    def __init__(self, configs_dir="configs", out_dir="reports/orders", auto_update=False, cache_dir="data/cache",
                 bundled_dir="data/bundled"):
        self.configs_dir = Path(configs_dir); self.out_dir = Path(out_dir)
        self.auto_update = auto_update; self.cache_dir = cache_dir; self.bundled_dir = bundled_dir
        self._lock = threading.Lock(); self._cache: dict = {}

    def config_path(self, profile: str) -> Path:
        p = self.configs_dir / f"soxl_{profile}.yaml"
        if not p.exists():
            p = self.configs_dir / f"{profile}.yaml"
        if not p.exists():
            raise FileNotFoundError(f"unknown profile: {profile}")
        return p

    def refresh(self, symbols=("SOXL", "SOXX")) -> dict:
        return {s: update_symbol(s, self.cache_dir, self.bundled_dir) for s in symbols}

    def run(self, profile: str, refresh=False, capital: float | None = None, start: str | None = None):
        cfg = load_config(self.config_path(profile))
        if capital: cfg.initial_capital = float(capital)
        if start: cfg.data.start = start
        key = (profile, capital, start)
        with self._lock:
            if refresh or (self.auto_update and key not in self._cache):
                self.refresh((cfg.data.symbol, cfg.data.reference))
                self._cache.clear()
            if key in self._cache:
                return self._cache[key]
            res = run_backtest(cfg)
            self._cache[key] = res
            return res

    def payload(self, res, fmt: str, env: str) -> tuple[str, str]:
        """(content-type, body). 파일도 저장."""
        if fmt == "kis":
            sheet = build_sheet(res, env=env); save_sheet(sheet, self.out_dir)
            return "application/json", json.dumps(sheet, ensure_ascii=False, indent=2)
        if fmt == "meritz":
            save_meritz_csv(res, self.out_dir)
            return "text/csv; charset=utf-8", meritz_csv_text(build_meritz_rows(res))
        f = res.frame
        body = {"trade_date": str(f.index[-1].date()), "close": float(f["close"].iloc[-1]),
                "stale_days": staleness_days(f.index[-1]), "equity": float(res.equity.iloc[-1]), "cash": float(res.final_cash),
                "bull": bool(f["bull"].iloc[-1]), "halted": bool(f["halted"].iloc[-1]) if "halted" in f else False,
                "orders": orders_table(res).to_dict(orient="records"), "baskets": state_table(res).to_dict(orient="records")}
        return "application/json", json.dumps(body, ensure_ascii=False, indent=2, default=str)


def make_handler(svc: OrderService, token: str | None):
    class H(BaseHTTPRequestHandler):
        def _send(self, code, ctype, body: str):
            data = body.encode("utf-8")
            self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data)))
            self.end_headers(); self.wfile.write(data)

        def do_GET(self):
            u = urlparse(self.path); q = {k: v[0] for k, v in parse_qs(u.query).items()}
            if token and (self.headers.get("X-Token") != token and q.get("token") != token):
                return self._send(401, "application/json", '{"error":"unauthorized"}')
            try:
                if u.path == "/health":
                    res = svc.run(q.get("profile", "balanced"))
                    last = res.frame.index[-1]
                    return self._send(200, "application/json", json.dumps({"ok": True, "last_close": str(last.date()),
                                                                           "stale_days": staleness_days(last)}))
                if u.path == "/orders":
                    res = svc.run(q.get("profile", "balanced"), refresh=q.get("refresh") == "1",
                                  capital=q.get("capital"), start=q.get("start"))
                    ctype, body = svc.payload(res, q.get("format", "json"), q.get("env", "paper"))
                    return self._send(200, ctype, body)
                return self._send(404, "application/json", '{"error":"not found"}')
            except Exception as e:  # noqa
                logger.exception("request failed")
                return self._send(500, "application/json", json.dumps({"error": str(e)}, ensure_ascii=False))

        def log_message(self, fmt, *args):
            logger.info("%s " + fmt, self.address_string(), *args)
    return H


def serve(host="127.0.0.1", port=8787, token=None, **kw):
    svc = OrderService(**kw)
    httpd = ThreadingHTTPServer((host, port), make_handler(svc, token))
    logger.info("qtrade serve on http://%s:%d (token=%s)", host, port, "set" if token else "none")
    httpd.serve_forever()
