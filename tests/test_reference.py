"""기준 전략(invest_strategy baseline/v5) 재구현이 원본 실행 결과와 일치하는지 확인.

data/bundled/reference_equity_cap1e8.csv 는 원본 코드(Gwangil/invest_strategy registry.create)를
같은 스냅샷·자본 1억으로 실행한 일별 총자산이다.
"""
import pandas as pd
import pytest

from qtrade.reference import run_reference, BASELINE, V5


@pytest.fixture(scope="module")
def data():
    soxl = pd.read_csv("data/bundled/SOXL.csv", index_col=0, parse_dates=True)
    ref = pd.read_csv("data/bundled/reference_equity_cap1e8.csv", index_col=0, parse_dates=True)
    return soxl, ref


@pytest.mark.parametrize("name,params", [("baseline", BASELINE), ("v5", V5)])
def test_reference_matches_original(data, name, params):
    soxl, ref = data
    mine, _, _ = run_reference(soxl["Close"], 1e8, params, rsi=soxl["RSI"])
    a, b = ref[name].align(mine, join="inner")
    assert len(a) == len(ref[name]) == len(mine)
    assert float((a - b).abs().max()) < 1.0   # 자본 1억 기준 부동소수 오차 (1e-8 상대)
