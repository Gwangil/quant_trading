"""범용 시뮬레이터, 추세 전략, 포트폴리오 결합, 전략 레지스트리."""
import numpy as np
import pandas as pd
import pytest

from qtrade.strategies import load_any, run_any, KINDS
from qtrade.strategies.regime_switch import SwitchConfig, SwitchRules, run_switch, switch_config_from_dict
from qtrade.config import DataConfig
from qtrade.portfolio import run_portfolio, combined_orders
from tests.test_core import make_data


def _switch_cfg(**rules):
    return SwitchConfig(name="s", initial_capital=100_000, cash_yield_annual=0.0,
                        data=DataConfig(source="csv"), rules=SwitchRules(ma_window=50, band=0.0, min_hold_days=1, **rules))


def test_sim_accounting_and_moc_fills():
    data = make_data(seed=8, n=600)
    res = run_switch(_switch_cfg(hold_when="bull"), data)
    f = res.frame
    np.testing.assert_allclose(f["equity"], f["cash"] + f["invested"])
    assert (f["cash"] >= -1e-6).all() and (f["exposure"] <= 1.0 + 1e-9).all()
    t = res.trades
    assert len(t) > 0 and set(t.kind) == {"MOC"}
    entries = t[t.reason == "switch_entry"]
    prev_bull = f["bull"].shift(1).reindex(entries.date)     # 진입은 강세 판정 다음 거래일 종가
    assert prev_bull.fillna(False).all()


def test_registry_loads_kind_and_runs(tmp_path):
    import yaml
    p = tmp_path / "s.yaml"
    yaml.safe_dump({"kind": "regime_switch", "name": "x", "initial_capital": 1000, "cash_yield_annual": 0.0,
                    "data": {"source": "csv", "cache_dir": "data/cache"}, "rules": {"ma_window": 50, "hold_when": "always"}}, open(p, "w"))
    cfg, kind = load_any(p)
    assert kind == "regime_switch" and cfg.rules.ma_window == 50 and set(KINDS) == {"basket_loc", "regime_switch"}
    with pytest.raises(KeyError):
        switch_config_from_dict({"nope": 1})


def test_portfolio_combines_sleeves_and_orders(tmp_path):
    import yaml
    from qtrade.config import save_config
    from tests.test_core import base_cfg
    bc = base_cfg(**{"data.source": "csv"}); save_config(bc, tmp_path / "b.yaml")
    tc = _switch_cfg(hold_when="always"); yaml.safe_dump(tc.to_dict(), open(tmp_path / "t.yaml", "w"))
    spec = {"name": "p", "initial_capital": 100_000, "rebalance": "yearly",
            "sleeves": [{"name": "basket", "config": str(tmp_path / "b.yaml"), "weight": 0.5}, {"name": "hold", "config": str(tmp_path / "t.yaml"), "weight": 0.5}]}
    out = run_portfolio(spec)
    assert set(out["equities"].columns) == {"basket", "hold"} and len(out["portfolio"]) > 100
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



def test_rebalance_orders_emitted_on_year_boundary_and_band(tmp_path):
    import yaml
    from qtrade.config import save_config
    from qtrade.portfolio import rebalance_orders
    from tests.test_core import base_cfg
    bc = base_cfg(**{"data.source": "csv"}); save_config(bc, tmp_path / "b.yaml")
    tc = _switch_cfg(hold_when="always"); yaml.safe_dump(tc.to_dict(), open(tmp_path / "t.yaml", "w"))
    sl = [{"name": "basket", "config": str(tmp_path / "b.yaml"), "weight": 0.7}, {"name": "hold", "config": str(tmp_path / "t.yaml"), "weight": 0.3}]
    out = run_portfolio({"name": "p", "initial_capital": 100_000, "rebalance": "band", "rebalance_band": 0.0, "sleeves": sl})
    ro = rebalance_orders(out)                       # 밴드 0 → 항상 이탈 → 주문 발생
    kinds = {r["kind"] for r in ro}
    assert "CAPITAL" in kinds and any(r["symbol"] == "SOXL" and r["side"] == "RESET" for r in ro)
    hold = [r for r in ro if r["sleeve"] == "hold"]
    assert hold and hold[0]["kind"] == "MOC" and hold[0]["side"] in ("BUY", "SELL") and hold[0]["qty"] > 0
    out_y = run_portfolio({"name": "p", "initial_capital": 100_000, "rebalance": "yearly", "sleeves": sl})
    last = out_y["equities"].index[-1]
    due = (last + pd.offsets.BDay(1)).year != last.year
    assert bool(rebalance_orders(out_y)) == due
