# 03. 실전 운용 절차

## 매일 루틴 (한국시간 기준, 미국 장 마감 후 아침)

```bash
source .venv/bin/activate
qtrade orders -c configs/soxl_basket.yaml -o reports/orders
```

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
- 같은 날 매수·매도가 동시에 나올 수 있다(서로 다른 가격대이므로 둘 다 넣는다).
- 증권사 앱에서 LOC/MOC 를 지원하는지 확인한다(국내 주요 증권사 미국주식 주문창에서 LOC/MOC 선택 가능).

## 상태 관리 방식

이 도구는 별도 포지션 파일을 두지 않고, `configs/*.yaml` 의 `start` 와 `initial_capital` 로
**전 구간을 재현(replay)** 해 오늘의 바스켓 상태와 내일 주문을 만든다.

- 실제 체결이 시뮬레이션과 달라졌다면(미체결, 수량 반올림 등) 가장 간단한 복구는
  **현재 시점을 새 시작일로 잡고 `initial_capital` 을 현재 총자산으로 바꿔 새 라운드로 시작**하는 것이다.
- 입출금이 있으면 같은 방식으로 `initial_capital` 을 갱신한다.
- 주문 수량은 정수 주로 내림한다(`orders.py`). 소액 계좌는 슬라이스가 1주 미만이 될 수 있으니 `slices` 를 줄인다.

## 점검 주기

| 주기 | 할 일 |
|---|---|
| 매일 | 주문표 생성 → 주문 입력 → 다음 날 체결 확인 |
| 매월 | `qtrade backtest -c configs/soxl_basket.yaml` 로 최신 데이터까지의 성과·MDD 확인 |
| 분기 | `qtrade sweep` 으로 파라미터 안정성 점검(학습/검증 분리). 상위 조합이 크게 바뀌면 원인(레짐 변화)을 먼저 확인 |
| 레짐 전환 시 | 약세 전환일에 `regime_bear` MOC 청산이 나오는지 확인. 이 규칙이 MDD 방어의 핵심이므로 임의로 건너뛰지 않는다 |

## 리스크 규칙 (임의 변경 금지 목록)

1. 바스켓 손절(`basket_sl_pct`)과 강제 시간청산(`hard_max_hold_days`)은 끄지 않는다.
2. 약세장에서 바스켓 수(`bear_max_baskets`)를 늘리지 않는다.
3. 예산 합(`budget_frac × count`)이 1을 크게 넘지 않게 한다(현금 한도로 잘리지만 급락 시 노출이 빨리 커진다).
