import numpy as np
import pandas as pd
import pytest

from qtrade.engine import run_backtest
from qtrade.tax import after_tax, realized_gains_krw, load_fx, TaxParams
from tests.test_core import make_data, base_cfg


def test_realized_gain_uses_trade_date_fx():
    idx = pd.bdate_range("2024-01-01", periods=3)
    fx = pd.Series([1000.0, 1200.0, 1100.0], idx)
    trades = pd.DataFrame([
        {"date": idx[0], "side": "BUY", "value": 1000.0, "fee": 1.0, "pnl": np.nan, "lots": None},
        {"date": idx[1], "side": "SELL", "value": 1100.0, "fee": 1.1, "pnl": 98.9, "lots": [(10.0, 100.0, idx[0])]},
    ])
    g = realized_gains_krw(trades, fx)
    # 매도 (1100-1.1)*1200 − 매입 10*100*(1+0.001)*1000
    assert g.gain_krw.iloc[0] == pytest.approx((1100 - 1.1) * 1200 - 1001.0 * 1000)


def test_after_tax_is_below_pre_tax_and_fx_scales_krw():
    data = make_data(seed=4)
    res = run_backtest(base_cfg(**{"cash_yield_annual": 0.04, "initial_capital": 1_000_000}), data)
    fx = pd.Series(1300.0, index=res.equity.index)
    out = after_tax(res, TaxParams(fx_spread_pct=0.0), fx=fx)
    np.testing.assert_allclose(out["krw_pre"].values, res.equity.values * 1300)
    assert out["krw_after"].iloc[-1] < out["krw_pre"].iloc[-1]
    assert out["total_capital_gains_tax_krw"] > 0 and out["total_dividend_tax_krw"] > 0
    assert (out["krw_after"] <= out["krw_pre"] + 1e-6).all()
    y = out["yearly"]
    assert (y.tax_assessed_krw >= 0).all() and abs(y.tax_paid_krw.sum() + out["unpaid_tax_krw"] - out["total_capital_gains_tax_krw"]) < 1
    # 부채 계상 방식: 세후 곡선의 일간 하락이 세전보다 크게 튀는 날(납부일 급락)이 없어야 함
    d = (out["krw_after"].pct_change() - out["krw_pre"].pct_change()).dropna()
    assert d.min() > -0.05


def test_fx_fallback_interpolates_annual_table():
    idx = pd.bdate_range("2023-01-02", periods=300)
    fx, src = load_fx(idx, cache_dir="/nonexistent")
    assert "annual" in src and fx.notna().all() and 1200 < fx.mean() < 1450
