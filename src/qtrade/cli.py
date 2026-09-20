"""CLI: qtrade backtest | sweep | orders"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import load_config


def _backtest(a):
    from .strategies import load_any, run_any
    from .report import write_report, render_markdown
    cfg, kind = load_any(a.config)
    res = run_any(cfg, kind)
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
    from .strategies import load_any
    cfg, _kind = load_any(a.config)
    orders, state, res = generate(cfg, a.out, env=a.env, fmt=a.format)
    print(render(orders, state, res))


def _tax(a):
    from .engine import run_backtest
    from .tax import write, render, TaxParams
    cfg = load_config(a.config)
    if a.capital: cfg.initial_capital = a.capital
    res = run_backtest(cfg)
    params = TaxParams(capital_gains_rate=a.rate, basic_deduction_krw=a.deduction, dividend_rate=a.dividend_rate, fx_spread_pct=a.fx_spread)
    out = write(res, a.out, a.name or cfg.name, params)
    print(render(out, a.name or cfg.name)); print(f"-> {Path(a.out) / (a.name or cfg.name)}_tax.md")


def _portfolio(a):
    from .portfolio import write, render, combined_orders
    out = write(a.spec, a.out)
    print(render(out, out["spec"].get("name", "portfolio")))
    print("## 통합 주문서 (다음 거래일)\n" + combined_orders(out).to_string(index=False))


def _serve(a):
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from .serve import serve
    serve(a.host, a.port, a.token, configs_dir=a.configs, out_dir=a.out, auto_update=a.update)


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


def _walkforward(a):
    import yaml
    from .walkforward import walk_forward, render, DEFAULT_WINDOWS
    cfg = load_config(a.config)
    raw = yaml.safe_load(open(a.grid, encoding="utf-8"))
    grid = raw["grid"]; windows = [tuple(w) for w in raw.get("windows", DEFAULT_WINDOWS)]
    out = walk_forward(cfg, grid, windows, mdd_gate=raw.get("mdd_gate", -0.40), by=raw.get("by", "calmar"),
                       workers=a.workers, fixed=raw.get("fixed", {}))
    Path(a.out).mkdir(parents=True, exist_ok=True)
    out["table"].to_csv(Path(a.out) / f"{a.name}.csv", index=False)
    out["wf_equity"].to_csv(Path(a.out) / f"{a.name}_equity.csv")
    md = render(out, a.name); (Path(a.out) / f"{a.name}.md").write_text(md, encoding="utf-8"); print(md)


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
    o.add_argument("--env", default=None, choices=["paper", "real"], help="auto_trade 주문서 JSON 의 집행 환경")
    o.add_argument("--format", default="all", choices=["kis", "meritz", "all"], help="집행기 형식 (-o 지정 시 저장)")
    o.set_defaults(fn=_orders)
    t = sp.add_parser("tax", help="세후 원화 지표 (달러/원화/세후 원화 나란히)")
    t.add_argument("-c", "--config", required=True); t.add_argument("-o", "--out", default="reports/tax"); t.add_argument("-n", "--name", default=None)
    t.add_argument("--capital", type=float, default=None, help="초기자본(USD) 덮어쓰기 — 기본공제 250만원의 상대 크기가 달라짐")
    t.add_argument("--rate", type=float, default=0.22); t.add_argument("--deduction", type=float, default=2_500_000)
    t.add_argument("--dividend-rate", type=float, default=0.154); t.add_argument("--fx-spread", type=float, default=0.001)
    t.set_defaults(fn=_tax)
    pf = sp.add_parser("portfolio", help="다전략 슬리브 결합 백테스트 + 통합 주문서")
    pf.add_argument("spec", help="포트폴리오 YAML (sleeves: [{config, weight}])"); pf.add_argument("-o", "--out", default="reports/portfolio")
    pf.set_defaults(fn=_portfolio)
    sv = sp.add_parser("serve", help="주문서 발급 HTTP 서버 (집행기 스케줄러가 호출)")
    sv.add_argument("--host", default="127.0.0.1"); sv.add_argument("--port", type=int, default=8787)
    sv.add_argument("--token", default=None, help="X-Token 헤더 / ?token= 공유 비밀")
    sv.add_argument("--configs", default="configs"); sv.add_argument("--out", default="reports/orders")
    sv.add_argument("--update", action="store_true", help="요청 시 yfinance 로 시세 자동 갱신 (첫 요청/refresh=1)")
    sv.set_defaults(fn=_serve)
    d = sp.add_parser("data", help="시세 데이터 관리")
    dsp = d.add_subparsers(dest="data_cmd", required=True)
    du = dsp.add_parser("update", help="yfinance 최신 일봉 + 번들 스냅샷 이어붙여 data/cache 에 저장")
    du.add_argument("symbols", nargs="*", default=["SOXL", "SOXX", "USDKRW"], help="USDKRW 는 야후 KRW=X (원/달러)")
    du.add_argument("--cache-dir", default="data/cache")
    du.add_argument("--bundled-dir", default="data/bundled")
    du.set_defaults(fn=_data_update)
    m = sp.add_parser("make-configs", help="프로필 정의(profiles.py)로부터 configs/*.yaml 재생성")
    m.add_argument("-o", "--out", default="configs")
    m.set_defaults(fn=_make_configs)
    w = sp.add_parser("walkforward", help="롤링 워크포워드 (창별 파라미터 재선정)")
    w.add_argument("-c", "--config", required=True); w.add_argument("-g", "--grid", required=True)
    w.add_argument("-o", "--out", default="reports/walkforward"); w.add_argument("-n", "--name", default="walkforward")
    w.add_argument("--workers", type=int, default=None); w.set_defaults(fn=_walkforward)
    c = sp.add_parser("compare", help="기준 전략(baseline/v5) 과 프로필 비교표 생성")
    c.add_argument("-o", "--out", default="reports")
    c.add_argument("--capital", type=float, default=100_000_000.0)
    c.set_defaults(fn=_compare)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
