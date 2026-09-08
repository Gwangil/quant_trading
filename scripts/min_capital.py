"""최소 시작 자산 검토: 정수 주 제약(1주 미만 주문 건너뜀) 하에서 자본 규모별 성과 열화를 측정.

- 창: OOS 2018-01 ~ 2026-07 (실데이터), 가격은 창의 중앙값이 '기준가'(기본: 마지막 종가)가 되도록 스케일 →
  "오늘 가격 수준에서 이 자본으로 운용하면" 을 근사. 스케일 없는 원값 실행도 같이 출력.
- 기준: 같은 자본의 소수점 주 실행 대비 CAGR 차이, 건너뛴 주문 비율, 투자비중.
사용: python scripts/min_capital.py [--fx 1400]
"""
from __future__ import annotations
import argparse, sys
sys.path.insert(0, "src")
import numpy as np, pandas as pd
from qtrade.profiles import build
from qtrade.data import build_dataset
from qtrade.engine import run_backtest
from qtrade.metrics import compute_metrics

CAPITALS = [2_000, 3_000, 5_000, 7_000, 10_000, 15_000, 20_000, 30_000, 50_000, 100_000, 300_000]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--fx", type=float, default=1400.0)
    ap.add_argument("--ref-price", type=float, default=None, help="기준가(USD). 기본: 마지막 종가")
    ap.add_argument("--start", default="2018-01-01")
    a = ap.parse_args()
    base = build("balanced", "hybrid")
    full = build_dataset(base.data)
    ref_price = a.ref_price or float(full["close"].iloc[-1])
    win = full[full.index >= pd.Timestamp(a.start) - pd.Timedelta(days=400)].copy()   # 지표 워밍업 포함
    scale = ref_price / float(win.loc[a.start:, "close"].median())
    scaled = win.copy(); scaled["close"] *= scale
    rows = []
    # 소수점 주 기준은 자본 무관하므로 프로필·가격모드당 1회만 계산
    for profile in ["defensive", "balanced", "aggressive"]:
        for label, d in (("scaled", scaled), ("raw", win)):
            dd = d[d.index >= pd.Timestamp(a.start) - pd.Timedelta(days=400)]
            cfg = build(profile, "hybrid"); cfg.data.start = a.start
            base_frac = None
            for cap in CAPITALS:
                c = build(profile, "hybrid"); c.data.start = a.start; c.initial_capital = cap
                if base_frac is None:
                    c.costs.integer_shares = False
                    r = run_backtest(c, dd); m = compute_metrics(r.equity, r.frame["exposure"])
                    base_frac = dict(cagr=m["cagr"], mdd=m["mdd"], expo=m["avg_exposure"])
                c.costs.integer_shares = True
                r = run_backtest(c, dd); m = compute_metrics(r.equity, r.frame["exposure"])
                skip = r.n_skipped_orders / r.n_fillable_orders if r.n_fillable_orders else 0.0
                rows.append(dict(profile=profile, price_mode=label, capital_usd=cap, capital_krw_m=round(cap * a.fx / 1e6),
                                 cagr=m["cagr"], cagr_frac=base_frac["cagr"], cagr_gap=m["cagr"] - base_frac["cagr"],
                                 mdd=m["mdd"], mdd_frac=base_frac["mdd"], expo=m["avg_exposure"], expo_frac=base_frac["expo"],
                                 skipped_ratio=skip, fills=len(r.trades)))
    out = pd.DataFrame(rows)
    out.to_csv("reports/min_capital.csv", index=False)
    pd.set_option("display.width", 220)
    print(f"기준가 {ref_price:.2f} USD, 창 {a.start}~, 스케일 {scale:.3f}, 환율 {a.fx:.0f}")
    print(out[out.price_mode == "scaled"].round(4).to_string(index=False))
    print(out[out.price_mode == "raw"].round(4).to_string(index=False))


if __name__ == "__main__":
    main()
