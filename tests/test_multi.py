"""범용 시뮬레이터, 추세 전략, 포트폴리오 결합, 전략 레지스트리."""
import numpy as np
import pandas as pd
import pytest

from qtrade.strategies import load_any, run_any, KINDS
from qtrade.strategies.trend import TrendConfig, TrendRules, run_trend
from qtrade.config import DataConfig
from qtrade.portfolio import run_portfolio, combined_orders
from tests.test_core import make_data


def _trend_cfg(**rules):
    return TrendConfig(name="t", initial_capital=100_000, cash_yield_annual=0.0,
                       data=DataConfig(source="csv"), rules=TrendRules(ma_window=50, mom_window=20, **rules))


def test_sim_accounting_and_moc_fills():
    data = make_data(seed=8, n=600)
    res = run_trend(_trend_cfg(), data)
    f = res.frame
    np.testing.assert_allclose(f["equity"], f["cash"] + f["invested"])
    assert (f["cash"] >= -1e-6).all() and (f["exposure"] <= 1.0 + 1e-9).all()
    t = res.trades
    assert len(t) > 0 and set(t.kind) == {"MOC"}
    # 진입은 기준지수가 이평 위인 날의 다음 거래일에만
    entries = t[t.reason == "trend_entry"]
    prev_bull = f["bull"].shift(1).reindex(entries.date)
    assert prev_bull.fillna(False).all()


def test_trend_trailing_stop_exits_after_drawdown_from_high():
    idx = pd.bdate_range("2015-01-01", periods=400)
    path = np.concatenate([np.linspace(100, 200, 250), np.linspace(200, 120, 150)])
    data = pd.DataFrame({"close": path, "ref_close": path}, index=idx)
    res = run_trend(_trend_cfg(trail_pct=0.20, exit_band=0.5), data)   # 이평 청산은 사실상 끔 → 추적 손절만
    exits = res.trades[res.trades.reason == "trend_exit"]
    assert len(exits) >= 1
    d = exits.date.iloc[0]
    assert data.loc[d, "close"] <= 200 * 0.80 * 1.02


def test_registry_loads_kind_and_runs(tmp_path):
    import yaml
    p = tmp_path / "t.yaml"
    yaml.safe_dump({"kind": "trend", "name": "x", "initial_capital": 1000, "cash_yield_annual": 0.0,
                    "data": {"source": "csv", "cache_dir": "data/cache"}, "rules": {"ma_window": 50}}, open(p, "w"))
    cfg, kind = load_any(p)
    assert kind == "trend" and cfg.rules.ma_window == 50 and "basket_loc" in KINDS
    with pytest.raises(KeyError):
        load_any(p) if False else __import__("qtrade.strategies.trend", fromlist=["trend_config_from_dict"]).trend_config_from_dict({"nope": 1})


def test_portfolio_combines_sleeves_and_orders(tmp_path):
    import yaml
    from qtrade.config import save_config
    from tests.test_core import base_cfg
    bc = base_cfg(**{"data.source": "csv"}); save_config(bc, tmp_path / "b.yaml")
    tc = _trend_cfg(); yaml.safe_dump(tc.to_dict(), open(tmp_path / "t.yaml", "w"))
    spec = {"name": "p", "initial_capital": 100_000, "rebalance": "yearly",
            "sleeves": [{"name": "basket", "config": str(tmp_path / "b.yaml"), "weight": 0.5}, {"name": "trend", "config": str(tmp_path / "t.yaml"), "weight": 0.5}]}
    out = run_portfolio(spec)
    assert set(out["equities"].columns) == {"basket", "trend"} and len(out["portfolio"]) > 100
    assert abs(out["portfolio"].iloc[0] - 100_000) < 1e-6
    assert out["corr"].shape == (2, 2)
    o = combined_orders(out)
    assert set(o.columns) >= {"symbol", "side", "kind", "limit", "qty", "sleeves"}
    # 위험균형: 비중 로그가 있고 매년 합이 1, 변동성 낮은 슬리브 비중이 높음
    spec_rp = {**spec, "rebalance": "risk_parity", "rp_lookback": 60}
    rp = run_portfolio(spec_rp)
    wl = rp["weight_log"]
    assert len(wl) >= 2 and np.allclose(wl.sum(axis=1), 1.0)
    vols = rp["equities"].pct_change().std()
    assert wl.iloc[-1][vols.idxmin()] >= wl.iloc[-1][vols.idxmax()]


def test_regime_switch_holds_only_in_selected_regime():
    from qtrade.strategies.regime_switch import SwitchConfig, SwitchRules, run_switch
    idx = pd.bdate_range("2015-01-01", periods=700)
    ref = np.concatenate([np.linspace(100, 150, 350), np.linspace(150, 80, 350)])          # 강세 → 약세
    data = pd.DataFrame({"close": np.linspace(50, 60, 700), "ref_close": ref}, index=idx)   # 자산은 완만 상승
    def cfg(hw):
        return SwitchConfig(name="s", initial_capital=10_000, cash_yield_annual=0.0, data=DataConfig(source="csv"),
                            rules=SwitchRules(hold_when=hw, ma_window=50, band=0.0, min_hold_days=1))
    bear = run_switch(cfg("bear"), data).frame; bull = run_switch(cfg("bull"), data).frame; alw = run_switch(cfg("always"), data).frame
    assert bear["exposure"].iloc[-1] > 0.9 and bear["exposure"].iloc[200] == 0.0
    assert bull["exposure"].iloc[200] > 0.9 and bull["exposure"].iloc[-1] == 0.0
    assert (alw["exposure"].iloc[60:] > 0.9).all()
