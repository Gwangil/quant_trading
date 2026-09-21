# quant_trading — 레버리지 ETF 다전략 개발·검증·주문서 발급 (일 1회 종가 주문)

> 미국 레버리지 ETF(기본: SOXL, 기준지수 SOXX)를 대상으로 **하루 한 번 종가 주문(LOC/MOC)** 만으로 운용하는
> 퀀트 전략의 설계 · 백테스트 · 주문서 발급 도구입니다. 실제 주문은 집행기(auto_trade / rpa_claude)가 맡습니다.
> 유효 전략은 두 가지입니다: **SOXL 분할 바스켓 LOC**, 그리고 그 위에 **GLD 30% 를 얹은 권장 포트폴리오** (docs/00).
> 이전 마이크로서비스 프로젝트는 `backup/old-main-msa` 브랜치에 보존되어 있습니다.

## 전략 한 줄 요약

**자산을 N개 바스켓으로 나누고, 바스켓마다 "떨어지면 사고(LOC 매수) · 오르면 판다(로트별 LOC 익절)"를 반복하되,
바스켓은 목표수익 / 손실한도 / 보유기간 중 하나로 주기적으로 전량 청산해 현금을 회수한다.
기준지수의 추세(200일선)로 약세장을 판정하면 동시 바스켓 수와 매수 규모를 줄여 MDD 를 관리한다.**

| 문서 | 내용 |
|---|---|
| [docs/00_strategies.md](docs/00_strategies.md) | **전략 설명서** — 유효 전략 2개의 규칙·성과·한계 (여기부터) |
| [docs/01_strategy_design.md](docs/01_strategy_design.md) | 전략 설계와 근거, 체결 모델 |
| [docs/02_backtest_results.md](docs/02_backtest_results.md) | 결과, 검증 기록(무엇이 무엇을 바꿨나), 워크포워드, 기준 전략 비교, 최소 자산 |
| [docs/03_live_operation.md](docs/03_live_operation.md) | **운용 매뉴얼** — 시작 설정, 매일/월/분기/연 루틴, 이상 상황 대응, 재설정 |
| [docs/04_roadmap.md](docs/04_roadmap.md) | 작업 요약·진행 상태·다음 단계 (작업 재개 시 여기부터) |
| [docs/05_execution_integration.md](docs/05_execution_integration.md) | 집행기(KIS auto_trade / Meritz rpa_claude) 주문서 규격·발급 방법·스케줄·선택 기준 |
| [docs/06_config_reference.md](docs/06_config_reference.md) | 설정 옵션 전체와 채택/기각 상태 (자동 생성) |
| [docs/07_multi_strategy.md](docs/07_multi_strategy.md) | 역할 경계, 다전략 구조, 전략 추가 절차, 슬리브 검증 결과(채택 1·기각 8) |
| [CLAUDE.md](CLAUDE.md) | 개발 규칙 |

## 설치

uv 사용 (권장, Windows/macOS/Linux 동일):

```powershell
uv venv
uv pip install -e ".[data,dev]"      # yfinance 포함
uv run pytest -q
uv run qtrade --help
```

기본 파이썬 사용:

```powershell
# Windows PowerShell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1        # 실행 정책 오류 시: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
python -m pip install -e ".[data,dev]"
```

```bash
# macOS / Linux
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[data,dev]"
```

설치 후 `qtrade` 명령이 생긴다(uv 는 `uv run qtrade`). `python -m qtrade ...` 로도 실행된다.

## 사용법

```bash
# 1) 백테스트 (번들 데이터: 네트워크 불필요)
qtrade backtest -c configs/soxl_balanced_cache.yaml -o reports    # 실제 SOXL/SOXX 2001~최신 (data/cache)
qtrade backtest -c configs/nasdaq3x_balanced.yaml -o reports      # 나스닥×3 프록시 1999~2018

# 2) 실제 SOXL/SOXX 최신 데이터로 백테스트 (yfinance + 번들 스냅샷 → data/cache)
qtrade data update
qtrade backtest -c configs/soxl_balanced.yaml -o reports

# 3) 파라미터 탐색 (IS/OOS 분리) / 롤링 워크포워드
qtrade sweep -c configs/soxl_balanced_cache.yaml -g configs/sweeps/sweep_merge_fine.yaml -o reports/sweeps --top 20
qtrade walkforward -c configs/soxl_balanced_cache.yaml -g configs/sweeps/walkforward_core.yaml

# 4) 다음 거래일 주문표 (+ KIS auto_trade JSON, Meritz rpa_claude CSV)
qtrade orders -c configs/soxl_balanced.yaml -o reports/orders --env paper
qtrade serve --port 8787 --token SECRET      # 집행기가 HTTP 로 발급받는 상주 모드 (docs/05)

# 5) 프로필 정의(src/qtrade/profiles.py)를 바꾼 뒤 설정 파일 재생성
qtrade make-configs

# 6) 영감이 된 baseline / v5 와 정면 비교표 생성
qtrade compare

# 6-1) 세후 원화 지표 (참고용; 의사결정은 세전 달러)
qtrade tax -c configs/soxl_balanced.yaml -o reports/tax

# 6-2) 다전략 포트폴리오 (슬리브 결합·상관·통합 주문서)
qtrade backtest -c configs/trend_soxl_cache.yaml -o reports
qtrade portfolio configs/portfolio_soxl_gld.yaml

# 7) 최소 시작 자산 검토 (정수 주 제약)
python scripts/min_capital.py --fx 1400
```

`python -m qtrade ...` 로도 실행됩니다.

## 프로젝트 구조

```
configs/            전략 설정(YAML). qtrade make-configs 로 profiles.py 에서 생성
  soxl_{defensive,balanced,aggressive}.yaml         실전 (data/cache, 2011~)
  soxl_*_cache.yaml                                  검증용 전 구간(2001~)
  gld_always.yaml, tlt_always.yaml                   슬리브
  portfolio_soxl_gld.yaml                            권장 다전략 (바스켓 70 + GLD 30); _gld_tlt 는 낙폭 최소 옵션
  nasdaq3x_*.yaml                                    나스닥×3 프록시 스트레스
  experiments/                                       기각·보류 검증 재현용
  sweeps/                                            탐색 그리드 (archive/ 는 제거 옵션 참조, 재실행 불가)
data/cache/         qtrade data update 결과 (SOXL/SOXX 2001~최신, git 추적: git add -f)
data/bundled/       스냅샷: SOXL/SOXX 하이브리드 ~2026-07, NASDAQ/SP500 1999-2018, T-bill 표
data/cache/         yfinance 캐시 (git 제외)
src/qtrade/
  config.py         설정 dataclass / YAML 로더 / 점 표기 오버라이드
  profiles.py       방어형/균형형/공격형 프로필 정의 (설정의 단일 원천)
  reference.py      기준 전략(baseline/v5) 재구현   compare.py   기준 전략 vs 프로필 비교
  tax.py            세후 원화 지표 (양도세·이자세·환율, qtrade tax)
  data.py           데이터 로딩, 레버리지 합성, 백필
  strategy.py       로트·바스켓 상태와 일간 주문 생성 규칙 (바스켓 전략의 핵심)
  engine.py         바스켓 전용 LOC/MOC 종가 체결 엔진
  sim.py            범용 포지션 시뮬레이터 (추세 등 kind 전략용)
  strategies/       kind 레지스트리(__init__), regime_switch.py 자산 보유 슬리브
  portfolio.py      슬리브 결합·상관·통합 주문서 (qtrade portfolio)
  metrics.py        단리/CAGR/MDD/회복기간/연도별 수익률
  report.py         마크다운 + 차트 리포트
  sweep.py          그리드 탐색 (멀티프로세스, 학습/검증 분리)
  walkforward.py    롤링 워크포워드 (창별 파라미터 재선정)
  updater.py        시세 갱신 (yfinance + 번들 스냅샷 splice, 미완성 봉 필터)
  sheet.py          집행기 주문서 내보내기 (KIS JSON, Meritz CSV, 동일가 합산)
  serve.py          주문서 발급 HTTP 서버 (qtrade serve)
  orders.py         실전 주문표 생성 (전 구간 재현 방식)
  cli.py            qtrade 명령 (backtest, sweep, walkforward, compare, tax, portfolio, orders, serve, data, make-configs)
scripts/            min_capital.py(최소 자산 검토), gen_config_reference.py(docs/06 생성)
tests/              pytest (26개: 엔진 불변식, 기준 전략 동등성, 갱신·파킹·주문서·서버, 세금, 시뮬레이터·포트폴리오)
reports/            생성된 리포트
docs/               설계 · 결과 · 운용 문서
```

## 결과 요약 (실제 SOXL/SOXX 2002~2026-09, 복리, 수수료 0.1%, 현금 80% 단기채 파킹)

| 프로필 | CAGR (USD) | **세후 KRW CAGR** | MDD | MDD 회복 | 최악 연도 | OOS 2018~ CAGR / MDD | 최소 자본 |
|---|---|---|---|---|---|---|---|
| 방어형 | 11.5% | **8.9%** | −19% | 389일 | −6% | 14.7% / −18% | 2,800만원 |
| 균형형 (기본) | 17.4% | **11.7%** | −28% | 401일 | −10% | 24.3% / −23% | 1,400만원 (권장 2,800만) |
| 공격형 | 20.9% | **9.6%** | −41% | 447일 | −30% | 35.0% / −37% | 2,800만원 |
| SOXL 보유 | 6.3% | | −99.6% | 4,397일 | −95% | 34.3% / −90.5% | |

세후 KRW = 양도세 22%·이자세 15.4%·환전 0.1% 반영 (docs/02 §7, 참고용). 세금은 회전이 많은 공격형을 가장 크게 깎아 세후로는 균형형이 낫다.

**권장 다전략 구성** `configs/portfolio_soxl_gld.yaml`: 균형형 바스켓 70% + GLD 상시 30% (연 1회 리밸런싱) → 2005~2026 CAGR 16.3%, MDD −19%, 최악 연도 −6%, Calmar 0.86 (바스켓 단독 0.64). 근거 docs/07 §4.3.

복리 프레임에서 방어형은 영감이 된 v5 전략(예산 복리화)을 모든 지표에서 앞선다. 단리(이익 인출) 프레임에서는 균형형과 v5 가 동률 수준이다 (docs/02 §5).
롤링 워크포워드 5개 창 검증 완료 (docs/02 §3.1).

전략 한 줄: **바스켓 4개로 나눠 하락일에 LOC 로 조금씩 사고, 반등일마다 로트 익절 + 10% 부분매도로 현금을 회수하며, SOXX 200일선 약세 전환 시 노출을 1/4 이하로 줄인다.** 대기 현금은 단기채에 파킹.
근거·탐색 기록·민감도는 docs/02, invest_strategy v5 와의 비교는 docs/02 §5.

## 주의

- 레버리지 ETF 는 변동성 붕괴(volatility decay)와 −90% 급의 낙폭이 실제로 발생했던 상품입니다. 백테스트 수익률은 미래를 보장하지 않습니다.
- 번들 프록시(NASDAQ×3 합성)는 실제 ETF 가 아니라 지수 수익률로 합성한 것으로, 실제 SOXL 은 별도 검증이 필요합니다.
