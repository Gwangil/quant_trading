"""백테스트 결과 리포트(markdown + PNG)."""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib import font_manager
import logging
logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)

_KO_FONTS = ["NanumGothic", "Malgun Gothic", "AppleGothic", "Noto Sans CJK KR", "WenQuanYi Zen Hei"]
_avail = {f.name for f in font_manager.fontManager.ttflist}
plt.rcParams["font.family"] = next((f for f in _KO_FONTS if f in _avail), "DejaVu Sans")
plt.rcParams["axes.unicode_minus"] = False

from .engine import BacktestResult
from .metrics import compute_metrics, buy_and_hold, fmt_pct
from .indicators import drawdown


def summarize(res: BacktestResult) -> dict:
    f = res.frame
    m = compute_metrics(res.equity, f["exposure"], res.baskets, res.trades)
    bh = buy_and_hold(f["close"], res.cfg.initial_capital)
    bh_ref = buy_and_hold(f["ref_close"], res.cfg.initial_capital)
    m["benchmark_symbol"] = compute_metrics(bh)
    m["benchmark_reference"] = compute_metrics(bh_ref)
    return m


def _row(label, m, keys):
    return "| " + label + " | " + " | ".join(keys(m)) + " |"


def render_markdown(res: BacktestResult, m: dict | None = None, title: str | None = None) -> str:
    m = m or summarize(res)
    cfg = res.cfg
    sym, ref = cfg.data.symbol, cfg.data.reference
    if cfg.data.synthetic is not None:
        syn = cfg.data.synthetic
        beta = f"×{syn.beta:g}" if syn.beta != 1.0 else ""
        sym = f"{ref}{beta}×{syn.leverage:g} 합성"
    keys = lambda d: [fmt_pct(d.get("simple_annual")), fmt_pct(d.get("cagr")), fmt_pct(d.get("mdd")),
                      str(d.get("mdd_recover_days") if d.get("mdd_recover_days") is not None else "미회복"),
                      str(d.get("max_underwater_days")), f"{d.get('sharpe', float('nan')):.2f}",
                      f"{d.get('calmar', float('nan')):.2f}", fmt_pct(d.get("worst_year")), fmt_pct(d.get("total_return"))]
    lines = [f"# {title or cfg.name}", "",
             f"- 기간: {m['start']} ~ {m['end']} ({m['years']}년), 초기자본 {cfg.initial_capital:,.0f}",
             f"- 매매 대상: {sym} / 기준지수: {ref} / 데이터 소스: {cfg.data.source}", "",
             "| 항목 | 단리 연수익 | CAGR | MDD | MDD 회복일수 | 최장 수중기간(일) | Sharpe | Calmar | 최악 연도 | 총수익 |",
             "|---|---|---|---|---|---|---|---|---|---|",
             _row("**전략**", m, keys),
             _row(f"{sym} 보유", m["benchmark_symbol"], keys),
             _row(f"{ref} 보유", m["benchmark_reference"], keys), ""]
    lines += ["## 운용 통계",
              f"- 평균 투자비중 {fmt_pct(m.get('avg_exposure'))}, 체결 {m.get('n_trades', 0)}건, "
              f"종료 바스켓 {m.get('n_baskets_closed', 0)}개 (승률 {fmt_pct(m.get('basket_win_rate'))}, "
              f"평균 수익률 {fmt_pct(m.get('basket_avg_ret'))}, 평균 보유 {m.get('basket_avg_hold_days', float('nan')):.0f}일)",
              f"- 바스켓 종료 사유: {m.get('basket_exit_reasons', {})}",
              f"- 10% 이상 낙폭 에피소드 {m.get('n_dd_episodes_10pct')}회, 평균 회복 {m.get('avg_recover_days_10pct', float('nan')):.0f}일",
              f"- 운용자 심리 지표: Ulcer {m.get('ulcer_index', float('nan')):.3f}, 최악의 달 {fmt_pct(m.get('worst_month'))}, "
              f"양(+)의 달 비율 {fmt_pct(m.get('pct_months_positive'))}, 최장 연속 손실 {m.get('max_losing_months_streak')}개월, "
              f"낙폭 10%/20% 초과 체류일 비율 {fmt_pct(m.get('pct_days_dd_gt10'))}/{fmt_pct(m.get('pct_days_dd_gt20'))}", ""]
    yr = m["yearly_returns"]; yb = m["benchmark_symbol"]["yearly_returns"]; yr2 = m["benchmark_reference"]["yearly_returns"]
    lines += ["## 연도별 수익률", "| 연도 | 전략 | " + sym + " | " + ref + " |", "|---|---|---|---|"]
    for y in yr:
        lines.append(f"| {y} | {fmt_pct(yr[y])} | {fmt_pct(yb.get(y))} | {fmt_pct(yr2.get(y))} |")
    lines += ["", "## 주요 설정",
              f"- 바스켓 {cfg.baskets.count}개 × 슬라이스 {cfg.baskets.slices}회, 오픈 간격 {cfg.baskets.min_days_between_opens}일",
              f"- 매수: 전일종가 × (1 − clamp({cfg.entry.dip_vol_mult}×σ, {cfg.entry.min_dip_pct:.0%}, {cfg.entry.max_dip_pct:.0%})), 첫 슬라이스 하락률 {cfg.entry.first_slice_dip_pct:.1%}, 물타기 가속 {cfg.entry.depth_boost}",
              f"- 로트 익절: 매입가 × (1 + clamp({cfg.exit.lot_tp_vol_mult}×σ, {cfg.exit.min_lot_tp_pct:.0%}, {cfg.exit.max_lot_tp_pct:.0%}))",
              f"- 바스켓 청산: 목표 +{cfg.exit.basket_tp_pct:.0%} / 손절 {('-' + format(cfg.exit.basket_sl_pct, '.0%')) if cfg.exit.basket_sl_pct is not None else '없음'} / 보유 {cfg.exit.max_hold_days}일(손익≥{cfg.exit.soft_exit_pnl_pct:.0%}) / 강제 {cfg.exit.hard_max_hold_days}일",
              f"- 레짐: {'ON' if cfg.regime.enabled else 'OFF'} (기준지수 {cfg.regime.ma_window}일선, 약세장 바스켓 {cfg.regime.bear_max_baskets}개, 슬라이스 ×{cfg.regime.bear_slice_mult}, 신규매수중단={cfg.regime.bear_no_new_lots})",
              f"- v5 결합: 상승일 부분매도 {cfg.exit.upday_sell_frac:.0%}, 서킷브레이커 {('-' + format(cfg.regime.breaker_dd, '.0%') + ' / ' + str(cfg.regime.breaker_resume_sma) + '일선 복귀') if cfg.regime.breaker_dd else '없음'}",
              f"- 리스크 레이어: 변동성 타게팅 {('연 ' + format(cfg.risk.vol_target_annual, '.0%')) if cfg.risk.vol_target_annual else '없음'}, 노출 상한 {cfg.risk.max_exposure:.0%}, "
              f"낙폭 연동 축소 {(format(cfg.risk.dd_scale_start, '.0%') + '→' + format(cfg.risk.dd_scale_floor, '.0%') + ' 에서 ×' + str(cfg.risk.dd_scale_min_mult)) if cfg.risk.dd_scale_start is not None else '없음'}",
              f"- 비용: 수수료 {cfg.costs.commission_pct:.2%}/편도, 현금 파킹 {cfg.cash_yield_annual if isinstance(cfg.cash_yield_annual, str) else format(cfg.cash_yield_annual, '.1%')} × {cfg.cash_yield_fraction:.0%}", ""]
    return "\n".join(lines)


def plot(res: BacktestResult, path: str | Path, title: str | None = None) -> None:
    f = res.frame
    cfg = res.cfg
    bh = buy_and_hold(f["close"], cfg.initial_capital)
    bh_ref = buy_and_hold(f["ref_close"], cfg.initial_capital)
    fig, axes = plt.subplots(4, 1, figsize=(13, 14), sharex=True,
                             gridspec_kw={"height_ratios": [3, 1.3, 1, 1]})
    ax = axes[0]
    ax.plot(res.equity.index, res.equity, label="전략", lw=1.6, color="#1f77b4")
    ax.plot(bh.index, bh, label=f"{cfg.data.symbol} 보유", lw=1, alpha=.7, color="#d62728")
    ax.plot(bh_ref.index, bh_ref, label=f"{cfg.data.reference} 보유", lw=1, alpha=.7, color="#7f7f7f")
    ax.set_yscale("log"); ax.legend(loc="upper left"); ax.grid(alpha=.3)
    ax.set_title(title or cfg.name)
    ax = axes[1]
    ax.fill_between(f.index, drawdown(res.equity) * 100, 0, color="#1f77b4", alpha=.5, label="전략 DD")
    ax.plot(f.index, drawdown(bh) * 100, color="#d62728", lw=.8, alpha=.7, label=f"{cfg.data.symbol} DD")
    ax.set_ylabel("낙폭 %"); ax.legend(loc="lower left"); ax.grid(alpha=.3)
    ax = axes[2]
    ax.fill_between(f.index, f["exposure"] * 100, 0, color="#2ca02c", alpha=.5)
    ax.set_ylabel("투자비중 %"); ax.set_ylim(0, 105); ax.grid(alpha=.3)
    ax2 = ax.twinx(); ax2.plot(f.index, f["n_active"], color="k", lw=.7); ax2.set_ylabel("활성 바스켓")
    ax = axes[3]
    ax.fill_between(f.index, f["bull"].astype(int), 0, color="#ff7f0e", alpha=.4, step="pre")
    ax.set_ylabel("강세(1)/약세(0)"); ax.set_ylim(-.05, 1.05); ax.grid(alpha=.3)
    fig.tight_layout()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=110)
    plt.close(fig)


def write_report(res: BacktestResult, out_dir: str | Path, name: str | None = None, title: str | None = None) -> dict:
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    name = name or res.cfg.name
    m = summarize(res)
    (out / f"{name}.md").write_text(render_markdown(res, m, title), encoding="utf-8")
    plot(res, out / f"{name}.png", title)
    res.trades.to_csv(out / f"{name}_trades.csv", index=False)
    res.baskets.to_csv(out / f"{name}_baskets.csv", index=False)
    res.frame.to_csv(out / f"{name}_daily.csv")
    return m
