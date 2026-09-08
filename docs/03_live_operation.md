# 03. 실전 운용 절차

## 최초 1회: 데이터 준비

```bash
pip install -e ".[data,dev]"
qtrade data update            # SOXL, SOXX 를 yfinance 로 받아 번들 스냅샷(2001~)과 이어붙여 data/cache/ 에 저장
qtrade backtest -c configs/soxl_balanced.yaml -o reports/live   # 최신 데이터로 프로필 재확인 (docs/02 와 비교)
```

`qtrade data update` 는 미완성 당일 봉(미 동부 16:10 이전)과 OHLC 불변식 위반 봉을 걸러낸다 (auto_trade updater 와 같은 규칙).
번들 구간은 이어붙이는 날의 종가 비율로 스케일하므로 수정주가가 바뀌어도 불연속이 생기지 않는다.

## 매일 루틴 (한국시간 기준, 미국 장 마감 후 아침)

```bash
qtrade data update
qtrade orders -c configs/soxl_balanced.yaml -o reports/orders --env paper   # 방어형은 soxl_defensive, 공격형은 soxl_aggressive
```

- 첫 줄에 `⚠ 데이터가 오래됨` 이 보이면 갱신이 안 된 것이다. 오래된 데이터로 만든 주문표는 쓰지 않는다.
- `--env paper|real` 을 주면 auto_trade 주문서 규격(v1) JSON 이 함께 저장된다:
  `reports/orders/orders_{env}_SOXL_soxl_balanced_{날짜}.json`. auto_trade 에서 `uv run auto-trade order execute --sheet <파일>` 로 집행한다
  (모의투자는 LOC/MOC 를 지정가로 자동 대체, 실전은 LOC/MOC 그대로). `meta.env` 가 집행 환경과 다르면 집행기가 중단한다.

출력 예:

```
기준일(마지막 종가): 2026-09-01  종가 31.20  레짐: 강세  일변동성 3.9%
총자산 108,420.00  현금 61,300.00  활성 바스켓 3

## 다음 거래일 주문 (종가 주문)
symbol side type  limit  qty  basket   reason
  SOXL SELL  LOC  33.10   95       2   lot_tp
  SOXL  BUY  LOC  30.59  204       2   dip_slice
  SOXL SELL  MOC   None  310       1   basket_tp
```

- **BUY LOC**: 지정가(limit) 로 LOC 매수. 종가가 limit 이하로 마감하면 체결.
- **SELL LOC**: 로트 익절. 종가가 limit 이상이면 체결.
- **SELL MOC**: 바스켓 전량 청산. 시장가 종가 주문.
- **SELL LOC (upday_sell)**: 상승일 부분매도. 지정가가 전일종가라서 오르면 체결, 내리면 미체결.
- 첫 줄에 `⚠ 서킷브레이커 발동 중` 이 보이면(공격형) 매수 주문이 없는 것이 정상이다.
- 같은 날 매수·매도가 동시에 나올 수 있다(서로 다른 가격대이므로 둘 다 넣는다).
- 증권사 앱에서 LOC/MOC 를 지원하는지 확인한다(국내 주요 증권사 미국주식 주문창에서 LOC/MOC 선택 가능).

## 상태 관리 방식

이 도구는 별도 포지션 파일을 두지 않고, `configs/*.yaml` 의 `start` 와 `initial_capital` 로
**전 구간을 재현(replay)** 해 오늘의 바스켓 상태와 내일 주문을 만든다.

- 실제 체결이 시뮬레이션과 달라졌다면(미체결, 수량 반올림 등) 가장 간단한 복구는
  **현재 시점을 새 시작일로 잡고 `initial_capital` 을 현재 총자산으로 바꿔 새 라운드로 시작**하는 것이다.
- 입출금이 있으면 같은 방식으로 `initial_capital` 을 갱신한다.
- 주문 수량은 정수 주로 내림한다(`orders.py`). 소액 계좌는 슬라이스가 1주 미만이 될 수 있으니 `slices` 를 줄인다.

## 페이퍼 트레이딩 절차 (실운용 전 30~60 거래일)

1. 시작일을 정하고 `configs/soxl_balanced.yaml` 의 `data.start` 를 그 날짜로, `initial_capital` 을 모의 자본으로 바꾼다 (또는 `qtrade make-configs` 후 수정).
2. 매일 아침 `qtrade data update` → `qtrade orders ... --env paper` → auto_trade 모의투자로 집행.
3. 다음 날 실제 체결을 `reports/orders/fills.csv` 에 기록한다. 열: `date,symbol,side,qty,price,fee,tag`. 이 파일이 로드맵 D(체결 기반 상태 보정)의 입력이 된다.
4. 주 1회 시뮬레이션 상태(`state_*.csv`)와 모의 계좌 잔고를 대조한다. 수량·평단 차이가 1% 를 넘으면 시작일·자본을 현재 값으로 재설정한다.
5. 30 거래일 후 체결가 오차(지정가 대비 평균 슬리피지)와 미체결 비율을 집계해 `costs.slippage_pct` 에 반영한다.

## 점검 주기

| 주기 | 할 일 |
|---|---|
| 매일 | 주문표 생성 → 주문 입력 → 다음 날 체결 확인 |
| 매월 | `qtrade backtest -c configs/soxl_balanced.yaml` 로 최신 데이터까지의 성과·MDD 확인 |
| 분기 | `qtrade sweep` 으로 파라미터 안정성 점검(학습/검증 분리). 상위 조합이 크게 바뀌면 원인(레짐 변화)을 먼저 확인 |
| 레짐 전환 시 | 약세 전환일에 `regime_bear` MOC 청산이 나오는지 확인. 이 규칙이 MDD 방어의 핵심이므로 임의로 건너뛰지 않는다 |

## 시작 자산

정수 주 제약 검토(docs/02 §6) 기준: 균형형 최소 $10k(≈1,400만원), 권장 $20k 이상. 방어형 권장 $50k, 공격형 $30k 이상.
소액이면 `baskets.slices` 를 4 로 줄여 슬라이스당 주수를 확보한다. 실제 주문표는 정수 주로 내림하므로 `qtrade orders` 결과에서 수량 0 인 주문이 자주 보이면 자본이 부족한 신호다.

## 프로필 선택 기준 (docs/02 §2)

| 프로필 | 이런 사람 | 각오해야 할 것 (백테스트 기준) |
|---|---|---|
| 방어형 | 낙폭 20% 를 넘기면 잠이 안 오는 사람, 자금이 큰 사람 | MDD −26%, 최악의 달 −15%, 연 10~17% |
| 균형형 | 기본 | MDD −36%, 최악의 달 −22%, 3년 중 1년은 마이너스 가능 |
| 공격형 | 낙폭 −45% 를 견디고 회복까지 1.5년을 기다릴 수 있는 사람 | MDD −43%, 최악의 달 −34% |

프로필은 자산이 빠진 뒤가 아니라 **시작 전에** 고른다. 낙폭 중에 방어형으로 바꾸는 것은 "낙폭 연동 축소"와 같은 행동이고, 백테스트상 회복을 4배 늦췄다.

## 운용자 심리 방어 규칙

1. **주문표를 그대로 넣는다.** 종가 주문이므로 장중 가격을 볼 이유가 없다. 하루 한 번, 정해진 시간에만 확인한다.
2. **낙폭은 설계된 값이다.** 균형형은 백테스트 기간의 16% 를 낙폭 20% 초과 상태로 보냈다. 낙폭 −20% 는 이상 신호가 아니라 예정된 상태다. 이상 신호는 "프로필의 MDD 를 넘어서는 낙폭" 뿐이다.
3. **프로필 MDD 를 넘으면 규칙을 바꾸는 게 아니라 멈춘다.** 원인(데이터·체결 오차·시장 구조 변화)을 백테스트로 확인한 뒤에만 재개한다.
4. **약세 전환 청산(`regime_bear`)을 건너뛰지 않는다.** 2008·2022 에서 계좌를 지킨 규칙이다.
5. **현금 비중이 80% 인 것은 정상이다.** 놀고 있는 것처럼 보이는 현금이 낙폭 −36% 를 만든 장본인이다. 단기채 ETF 파킹은 허용, 다른 종목 매수는 금지.
6. **월 1회만 성과를 본다.** 일 단위 손익 확인은 규칙 이탈의 가장 흔한 원인이다.

## 리스크 규칙 (임의 변경 금지 목록)

1. 강제 시간청산(`hard_max_hold_days`)과 약세 전환 청산(`bear_liquidate`)은 끄지 않는다.
2. 약세장에서 바스켓 수(`bear_max_baskets`)를 늘리지 않는다.
3. 상승일 부분매도(`upday_sell_frac`)를 0 으로 내리지 않는다 (MDD −52% 로 돌아간다).
4. 예산 합(`budget_frac × count`)이 1을 크게 넘지 않게 한다.
