import numpy as np
import pandas as pd
import pytest

from qtrade.config import StrategyConfig, DataConfig, SyntheticConfig, config_from_dict
from qtrade.data import synthetic_leveraged
from qtrade.engine import run_backtest
from qtrade.metrics import compute_metrics, drawdown_episodes
from qtrade.strategy import Basket, Lot


def make_data(n=800, seed=0, mu=0.0004, sigma=0.03):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2015-01-01", periods=n)
    ref = pd.Series(100 * np.cumprod(1 + rng.normal(mu / 3, sigma / 3, n)), idx)
    close = synthetic_leveraged(ref, SyntheticConfig(leverage=3))
    return pd.DataFrame({"close": close.values, "ref_close": ref.values}, index=idx)


def base_cfg(**over):
    cfg = StrategyConfig(name="t", initial_capital=100_000, data=DataConfig(source="bundled"))
    return cfg.with_overrides(over)


def test_synthetic_leverage_matches_daily_returns():
    idx = pd.bdate_range("2020-01-01", periods=5)
    ref = pd.Series([100, 101, 99, 99, 102.], idx)
    syn = synthetic_leveraged(ref, SyntheticConfig(leverage=3, expense_ratio=0, financing_rate=0))
    r = syn.pct_change().dropna().values
    np.testing.assert_allclose(r, 3 * ref.pct_change().dropna().values, atol=1e-12)


def test_basket_accounting():
    b = Basket(1, 1000.0, pd.Timestamp("2020-01-01"), 0)
    b.lots.append(Lot(10, 50.0, pd.Timestamp("2020-01-02"), 1))
    assert b.cost_basis() == 500 and b.cash_avail() == 500
    assert b.ret(60.0) == pytest.approx(100 / 1000)
    b.realized += 30
    assert b.cash_avail() == 530 and b.equity(50.0) == 1030


def test_engine_invariants_and_loc_semantics():
    data = make_data()
    cfg = base_cfg()
    res = run_backtest(cfg, data)
    f = res.frame
    assert (f["cash"] >= -1e-6).all()
    # 총자산 = 현금 + 평가액
    np.testing.assert_allclose(f["equity"], f["cash"] + f["invested"])
    # LOC 매수는 하락 마감일에만, LOC 매도는 지정가 이상에서만 체결
    t = res.trades.merge(f[["close"]], left_on="date", right_index=True)
    prev = f["close"].shift(1).rename("prev")
    t = t.merge(prev, left_on="date", right_index=True)
    buys = t[(t.side == "BUY") & (t.kind == "LOC")]
    assert (buys["close"] <= buys["prev"] * (1 + 1e-9)).all()
    sells = t[(t.side == "SELL") & (t.kind == "LOC")]
    assert (sells["pnl"] > 0).all()   # 로트 익절은 항상 매입가 위에서만 체결
    # 동시 활성 바스켓 수 제한
    assert f["n_active"].max() <= cfg.baskets.count
    # 종료된 바스켓은 사유가 있어야 함
    closed = res.baskets[res.baskets.status == "closed"]
    assert closed["reason"].notna().all()
    assert set(closed["reason"]).issubset({"basket_tp", "basket_sl", "time_soft", "time_hard", "regime_bear"})


def test_bear_regime_limits_baskets():
    data = make_data(seed=3)
    cfg = base_cfg(**{"regime.bear_max_baskets": 1, "regime.ma_window": 50})
    res = run_backtest(cfg, data)
    f = res.frame
    # 약세장에서 바스켓 수는 기존 것이 종료되며 1개로 수렴해야 하므로 신규 오픈은 1개 초과 불가
    opened = res.baskets.set_index("opened")
    bear_days = f.index[~f["bull"]]
    # 약세장에 오픈된 바스켓이 있다면 그 시점 활성 수는 1 이하
    for d in opened.index.intersection(bear_days):
        assert f.loc[d, "n_active"] <= 1


def test_time_stops_bound_holding_period():
    data = make_data(seed=5)
    cfg = base_cfg(**{"exit.max_hold_days": 20, "exit.hard_max_hold_days": 40, "exit.basket_tp_pct": 9.0})
    res = run_backtest(cfg, data)
    closed = res.baskets[res.baskets.status == "closed"]
    assert (closed["hold_days"] <= 41).all()


def test_metrics_mdd_and_recovery():
    idx = pd.bdate_range("2020-01-01", periods=6)
    eq = pd.Series([100, 120, 60, 90, 130, 125.], idx)
    m = compute_metrics(eq)
    assert m["mdd"] == pytest.approx(-0.5)
    assert m["mdd_recovery"] == idx[4].date().isoformat()
    eps = drawdown_episodes(eq, 0.1)
    assert len(eps) == 1 and bool(eps.loc[0, "recovered"])


def test_config_roundtrip_and_overrides():
    cfg = config_from_dict({"name": "x", "exit": {"basket_tp_pct": 0.2}, "data": {"synthetic": {"leverage": 2}}})
    assert cfg.exit.basket_tp_pct == 0.2 and cfg.data.synthetic.leverage == 2
    cfg2 = cfg.with_overrides({"baskets.count": 3})
    assert cfg2.baskets.count == 3 and cfg.baskets.count == 5
    with pytest.raises(KeyError):
        config_from_dict({"nope": 1})


def test_regime_hysteresis_reduces_flips():
    from qtrade.engine import regime_flags
    from qtrade.indicators import sma
    idx = pd.bdate_range("2020-01-01", periods=300)
    rng = np.random.default_rng(1)
    ref = pd.Series(100 + np.cumsum(rng.normal(0, 1, 300)), idx)
    ma = sma(ref, 50)
    f0 = regime_flags(ref, ma, 0.0).dropna()
    f2 = regime_flags(ref, ma, 0.03).dropna()
    assert (f0.diff().abs().sum()) >= (f2.diff().abs().sum())
    assert set(f2.unique()).issubset({0.0, 1.0})
