"""CLI: qtrade backtest | sweep | orders"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import load_config


def _backtest(a):
    from .engine import run_backtest
    from .report import write_report, render_markdown
    cfg = load_config(a.config)
    res = run_backtest(cfg)
    m = write_report(res, a.out, a.name, a.title)
    print(render_markdown(res, m, a.title))
    print(f"-> {Path(a.out) / (a.name or cfg.name)}.md / .png")


def _sweep(a):
    from .sweep import run_sweep, rank, load_grid
    cfg = load_config(a.config)
    grid, opts = load_grid(a.grid)
    df = run_sweep(cfg, grid, split=opts.get("split", a.split), workers=a.workers)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / f"{a.name}.csv", index=False)
    ranked = rank(df, max_mdd=opts.get("max_mdd", a.max_mdd), by=opts.get("by", "simple_annual"))
    ranked.to_csv(out / f"{a.name}_ranked.csv", index=False)
    with __import__("pandas").option_context("display.width", 250, "display.max_columns", 40):
        print(ranked.head(a.top).to_string(index=False))
    print(f"-> {out / a.name}.csv, {out / a.name}_ranked.csv ({len(df)} combos)")


def _orders(a):
    from .orders import generate, render
    cfg = load_config(a.config)
    orders, state, res = generate(cfg, a.out, env=a.env)
    print(render(orders, state, res))


def _data_update(a):
    from .updater import update_symbol
    for sym in a.symbols:
        r = update_symbol(sym, a.cache_dir, a.bundled_dir)
        print(f"{r['symbol']}: {r['rows']}행 {r['first']}~{r['last']} (yfinance {r['fresh_from']}~) -> {r['path']}")


def _compare(a):
    from .compare import write, render, PERIODS
    table = write(a.out, a.capital)
    for period in PERIODS:
        print(f"\n## {period}\n" + render(table, period))
    print(f"-> {a.out}/compare_reference.md")


def _make_configs(a):
    from .profiles import write_all
    for w in write_all(a.out):
        print("wrote", w)


def main(argv=None):
    p = argparse.ArgumentParser(prog="qtrade", description="분할 바스켓 LOC 전략")
    sp = p.add_subparsers(dest="cmd", required=True)
    b = sp.add_parser("backtest", help="백테스트 실행 및 리포트 생성")
    b.add_argument("-c", "--config", required=True)
    b.add_argument("-o", "--out", default="reports")
    b.add_argument("-n", "--name", default=None)
    b.add_argument("-t", "--title", default=None)
    b.set_defaults(fn=_backtest)
    s = sp.add_parser("sweep", help="파라미터 그리드 탐색")
    s.add_argument("-c", "--config", required=True)
    s.add_argument("-g", "--grid", required=True)
    s.add_argument("-o", "--out", default="reports/sweeps")
    s.add_argument("-n", "--name", default="sweep")
    s.add_argument("--split", default=None, help="학습/검증 분리일 (YYYY-MM-DD)")
    s.add_argument("--max-mdd", type=float, default=-0.40)
    s.add_argument("--workers", type=int, default=None)
    s.add_argument("--top", type=int, default=20)
    s.set_defaults(fn=_sweep)
    o = sp.add_parser("orders", help="다음 거래일 주문표 생성")
    o.add_argument("-c", "--config", required=True)
    o.add_argument("-o", "--out", default=None)
    o.add_argument("--env", default=None, choices=["paper", "real"], help="auto_trade 주문서 JSON 도 저장 (집행 환경)")
    o.set_defaults(fn=_orders)
    d = sp.add_parser("data", help="시세 데이터 관리")
    dsp = d.add_subparsers(dest="data_cmd", required=True)
    du = dsp.add_parser("update", help="yfinance 최신 일봉 + 번들 스냅샷 이어붙여 data/cache 에 저장")
    du.add_argument("symbols", nargs="*", default=["SOXL", "SOXX"])
    du.add_argument("--cache-dir", default="data/cache")
    du.add_argument("--bundled-dir", default="data/bundled")
    du.set_defaults(fn=_data_update)
    m = sp.add_parser("make-configs", help="프로필 정의(profiles.py)로부터 configs/*.yaml 재생성")
    m.add_argument("-o", "--out", default="configs")
    m.set_defaults(fn=_make_configs)
    c = sp.add_parser("compare", help="기준 전략(baseline/v5) 과 프로필 비교표 생성")
    c.add_argument("-o", "--out", default="reports")
    c.add_argument("--capital", type=float, default=100_000_000.0)
    c.set_defaults(fn=_compare)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
