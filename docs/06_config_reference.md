# 06. 설정 레퍼런스 (자동 생성: `python scripts/gen_config_reference.py`)

YAML 은 `qtrade make-configs` 가 `src/qtrade/profiles.py` 에서 생성한다. 기본값은 **균형형 프로필과 같다**(테스트로 강제).
기각된 실험 옵션(손절, 물타기 가속, 부분 익절, 변동성 레짐, 노출 상한, 낙폭 연동 축소, 레짐 판정 방식 등)은 2026-09-21 정리 시 코드에서 제거했다. 근거와 수치는 docs/02 §3, docs/07 §4 에 남아 있다.

## `data.synthetic` (SyntheticConfig)

| 키 | 기본값 | 의미 | 상태 |
|---|---|---|---|
| `leverage` | `3.0` |  |  |
| `beta` | `1.0` | 기준 지수 대비 민감도 (반도체≈나스닥×1.3 같은 스트레스용) |  |
| `expense_ratio` | `0.0095` | 연 보수 (SOXL 0.95%) |  |
| `financing_rate` | `0.02` | 연 조달금리 (레버리지-1 배만큼 부담) |  |

## `data` (DataConfig)

| 키 | 기본값 | 의미 | 상태 |
|---|---|---|---|
| `symbol` | `"SOXL"` | 매매 대상 (레버리지 ETF) |  |
| `reference` | `"SOXX"` | 추세/변동성 판단용 기준 지수(무레버리지) |  |
| `source` | `"yfinance"` | yfinance | csv | bundled |  |
| `cache_dir` | `"data/cache"` | source=csv 일 때 읽는 곳 (qtrade data update 가 씀) |  |
| `bundled_dir` | `"data/bundled"` | 스냅샷·지수·금리표 |  |
| `start` | `None` | 매매 시작일 (지표 계산은 그 이전 데이터도 사용) |  |
| `end` | `None` | 매매 종료일 (None = 데이터 끝) |  |
| `synthetic` | `None` | 설정 시 symbol 가격을 reference로부터 합성 | 프록시용 |
| `backfill` | `False` | 실제 ETF 상장 이전 구간을 합성 가격으로 연장 | 백필용 |

## `baskets` (BasketConfig)

| 키 | 기본값 | 의미 | 상태 |
|---|---|---|---|
| `count` | `4` | 동시 운용 바스켓 수 = 자산 분할 수 |  |
| `slices` | `6` | 바스켓 예산을 나눠 사는 분할 매수 횟수 |  |
| `min_days_between_opens` | `3` | 바스켓 신규 오픈 간 최소 간격(거래일) → 진입 시점 분산 |  |
| `min_budget_frac` | `0.25` | 여유 현금이 정상 예산의 이 비율 미만이면 오픈하지 않음 |  |
| `budget_mode` | `"equity"` | equity: 현재 총자산 기준(복리) | fixed: 초기자본 기준 고정(단리) | 비교용(fixed) |

## `entry` (EntryConfig)

| 키 | 기본값 | 의미 | 상태 |
|---|---|---|---|
| `vol_window` | `20` | 일간 실현변동성 산출 창 |  |
| `dip_vol_mult` | `0.25` | 매수 LOC 지정가 = 전일종가 × (1 − mult × 일변동성) |  |
| `min_dip_pct` | `0.0` | 하락률 하한 (0 = 보합 이하 마감이면 체결) |  |
| `max_dip_pct` | `0.06` | 하락률 상한 |  |
| `first_slice_dip_pct` | `0.0` | 바스켓 첫 슬라이스는 이 하락률만 요구 (0 = 보합 이하면 매수) | 코어(0) |
| `max_slice_mult` | `3.0` | 슬라이스 배수 상한 (약세장 ×0.5, 변동성 타게팅 축소만 있으므로 사실상 1) |  |
| `target_vol` | `0.045` | 변동성 타게팅: 슬라이스 × min(1, target_vol/σ). 급변동기 매수 축소 (예: 0.04) |  |

## `exit` (ExitConfig)

| 키 | 기본값 | 의미 | 상태 |
|---|---|---|---|
| `lot_tp_vol_mult` | `1.0` | 로트 매도 LOC 지정가 = 로트 매입가 × (1 + mult × 일변동성) |  |
| `min_lot_tp_pct` | `0.03` | 익절률 하한 |  |
| `max_lot_tp_pct` | `0.15` | 익절률 상한 |  |
| `upday_sell_frac` | `0.1` | 상승 마감일마다 보유수량의 이 비율을 매도 (LOC 지정가 = 전일종가). invest_strategy v5 의 부분매도 |  |
| `basket_tp_pct` | `0.20` | 바스켓 수익률(예산 대비) 목표 → 전량 청산(MOC) |  |
| `basket_sl_pct` | `None # 바스켓 손실률 한도 → 전량 청산 (None=미사용. 실데이터에서 해로움, docs/02 §3)` |  | 기각(해로움) — None 유지 |
| `max_hold_days` | `60` | 보유기간 초과 시, 손익 ≥ soft_exit_pnl_pct 이면 청산 |  |
| `hard_max_hold_days` | `120` | 보유기간 초과 시 무조건 청산 |  |
| `soft_exit_pnl_pct` | `0.0` | max_hold_days 청산 조건이 되는 손익 하한 | 코어(0) |

## `regime` (RegimeConfig)

| 키 | 기본값 | 의미 | 상태 |
|---|---|---|---|
| `enabled` | `True` | 기준지수 추세 레짐 사용 |  |
| `ma_window` | `200` | 기준 지수 종가 vs 이동평균 → 강세/약세 |  |
| `ma_band` | `0.0` | 히스테리시스 밴드: 강세 전환은 MA×(1+band) 상향, 약세 전환은 MA×(1−band) 하향 돌파 | 코어(0) |
| `bear_max_baskets` | `1` | 약세장에서 동시 운용 가능한 바스켓 수 |  |
| `bear_slice_mult` | `0.5` | 약세장 슬라이스 크기 배수 |  |
| `bear_liquidate` | `True` | 약세 전환 시 bear_max_baskets 초과분(수익률 낮은 순)을 청산 |  |
| `cooldown_after_sl_days` | `20` | 바스켓 손절·약세 청산·브레이커 후 이 기간 동안 신규 바스켓 오픈 금지 |  |
| `breaker_dd` | `None` | 계좌 서킷브레이커: 총자산이 고점 대비 이 비율 이상 빠지면 전량 청산·매매 중단 (예: 0.15) | 공격형만 |
| `breaker_resume_sma` | `200` | 중단 해제: 매매 대상 종가가 이 이동평균 위로 복귀하면 재개 (고점은 현재 자산으로 리셋) |  |

## `costs` (CostConfig)

| 키 | 기본값 | 의미 | 상태 |
|---|---|---|---|
| `commission_pct` | `0.001` | 편도 수수료 (0.1%) |  |
| `slippage_pct` | `0.0` | 종가 체결이므로 기본 0 | 실측 후 설정 |
| `integer_shares` | `False` | True: 정수 주만 체결 (1주 미만 주문은 건너뜀). 소액 계좌 검토용 | 검토용 |

## `최상위` (StrategyConfig)

| 키 | 기본값 | 의미 | 상태 |
|---|---|---|---|
| `name` | `"basket_loc"` | 리포트·주문서 파일명에 쓰임 |  |
| `initial_capital` | `100_000.0 # 초기자본 (USD). 실운용은 계좌 총자산으로 설정` |  |  |
| `cash_yield_annual` | `0.0` | 대기 현금 수익률: 숫자(고정) 또는 "TBILL3M"(번들 연평균 T-bill 표) |  |
| `cash_yield_fraction` | `1.0` | 파킹 비율 (예: 0.8 = 현금의 80% 만 단기채, 20% 는 결제·주문 여유) |  |
| `cash_yield_spread` | `0.0` | 파킹 상품 보수·스프레드 (예: −0.0015) |  |
| `data` | `(하위 섹션)` |  |  |
| `baskets` | `(하위 섹션)` |  |  |
| `entry` | `(하위 섹션)` |  |  |
| `exit` | `(하위 섹션)` |  |  |
| `regime` | `(하위 섹션)` |  |  |
| `costs` | `(하위 섹션)` |  |  |

## 점 표기 오버라이드

탐색 그리드와 `with_overrides` 는 `섹션.키` 형태를 쓴다. 예: `exit.upday_sell_frac: 0.2`, `regime.breaker_dd: 0.25`.
