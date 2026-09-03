# quant_trading — 분할 바스켓 LOC 전략 (레버리지 ETF 일 1회 종가 주문)

> 미국 레버리지 ETF(기본: SOXL, 기준지수 SOXX)를 대상으로 **하루 한 번 종가 주문(LOC/MOC)** 만으로 운용하는
> 퀀트 전략의 설계 · 백테스트 · 실전 주문표 생성 도구입니다.
> 이전 마이크로서비스 프로젝트는 `backup/old-main-msa` 브랜치에 보존되어 있습니다.

## 전략 한 줄 요약

**자산을 N개 바스켓으로 나누고, 바스켓마다 "떨어지면 사고(LOC 매수) · 오르면 판다(로트별 LOC 익절)"를 반복하되,
바스켓은 목표수익 / 손실한도 / 보유기간 중 하나로 주기적으로 전량 청산해 현금을 회수한다.
기준지수의 추세(200일선)로 약세장을 판정하면 동시 바스켓 수와 매수 규모를 줄여 MDD 를 관리한다.**

자세한 설계 근거는 [docs/01_strategy_design.md](docs/01_strategy_design.md),
백테스트 결과는 [docs/02_backtest_results.md](docs/02_backtest_results.md),
실전 운용 절차는 [docs/03_live_operation.md](docs/03_live_operation.md) 를 보세요.

## 설치

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[data,dev]"      # yfinance 포함
pytest -q
```

## 사용법

```bash
# 1) 백테스트 (번들 데이터: 네트워크 불필요)
qtrade backtest -c configs/soxl_hybrid.yaml -o reports        # 실제 SOXL 하이브리드 2001~2026
qtrade backtest -c configs/proxy_nasdaq3x.yaml -o reports     # 나스닥×3 프록시 1999~2018

# 2) 실제 SOXL/SOXX 로 백테스트 (yfinance 로 내려받아 data/cache 에 저장)
qtrade backtest -c configs/soxl_basket.yaml -o reports

# 3) 파라미터 탐색 (학습/검증 분리 포함)
qtrade sweep -c configs/soxl_basket.yaml -g configs/sweep_core.yaml -o reports/sweeps --top 20

# 4) 다음 거래일 주문표
qtrade orders -c configs/soxl_basket.yaml -o reports/orders
```

`python -m qtrade ...` 로도 실행됩니다.

## 프로젝트 구조

```
configs/            전략 설정(YAML)과 탐색 그리드
  soxl_basket.yaml        실전 기본 설정 (SOXL / SOXX, yfinance) — 균형형
  soxl_aggressive.yaml    실전 공격형
  soxl_hybrid*.yaml       번들 SOXL 하이브리드 스냅샷(invest_strategy 출처)으로 같은 설정 검증
  proxy_nasdaq3x.yaml     번들 데이터 프록시 (NASDAQ×3 합성, 1999~2018)
  proxy_semi3x_stress.yaml 반도체 스트레스 프록시 (NASDAQ×1.3 민감도 ×3)
  sweep_*.yaml            파라미터 그리드
data/bundled/       오프라인 검증용 일봉: SOXL/SOXX 하이브리드 2001-2026, NASDAQ/SP500 1999-2018
data/cache/         yfinance 캐시 (git 제외)
src/qtrade/
  config.py         설정 dataclass / YAML 로더 / 점 표기 오버라이드
  data.py           데이터 로딩, 레버리지 합성, 백필
  strategy.py       로트·바스켓 상태와 일간 주문 생성 규칙 (전략의 핵심)
  engine.py         LOC/MOC 종가 체결 시뮬레이션, 자산·거래 기록
  metrics.py        단리/CAGR/MDD/회복기간/연도별 수익률
  report.py         마크다운 + 차트 리포트
  sweep.py          그리드 탐색 (멀티프로세스, 학습/검증 분리)
  orders.py         실전 주문표 생성 (전 구간 재현 방식)
  cli.py            qtrade 명령
tests/              pytest
reports/            생성된 리포트
docs/               설계 · 결과 · 운용 문서
```

## 결과 요약 (실제 SOXL 하이브리드, 2002~2026, 복리)

| 설정 | CAGR | MDD | OOS 2018~ CAGR / MDD | 2022년 |
|---|---|---|---|---|
| 균형형 | 15.3% | −33% | 26.9% / −18% | −4.7% |
| 공격형 | 23.8% | −49% | 42.0% / −36% | −18% |
| SOXL 보유 | 6.8% | −99.6% | 36.6% / −90.5% | −85.7% |

자세한 표와 invest_strategy v5 와의 비교는 docs/02 §5.

## 주의

- 레버리지 ETF 는 변동성 붕괴(volatility decay)와 −90% 급의 낙폭이 실제로 발생했던 상품입니다. 백테스트 수익률은 미래를 보장하지 않습니다.
- 번들 프록시(NASDAQ×3 합성)는 실제 ETF 가 아니라 지수 수익률로 합성한 것으로, 실제 SOXL 은 별도 검증이 필요합니다.
