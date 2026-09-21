# 03. 운용 매뉴얼

이 저장소는 **주문서를 발급**하는 곳이다. 주문 접수·체결 확인·잔고 관리는 집행기(auto_trade / rpa_claude)가 한다(docs/05). 이 매뉴얼은 주문서 발급 쪽에서 매일·매월·매년 해야 할 일과 이상 상황 대응을 적는다.

## 1. 시작 전 결정

| 항목 | 기본 | 비고 |
|---|---|---|
| 구성 | **전략 B: 바스켓 균형형 70 + GLD 30** (`configs/portfolio_soxl_gld.yaml`) | 바스켓 단독은 `configs/soxl_balanced.yaml` |
| 프로필 | 균형형 | 방어형(낙폭 −19%), 공격형(권하지 않음). 낙폭 중에 바꾸지 않는다 — 시작 전에 정한다 |
| 자본 | 균형형 최소 $10k, 권장 $20k 이상 | 정수 주 제약 검토 docs/02 §6 |
| 집행기 | KIS(API) 또는 Meritz(RPA) | 비교 기준 docs/05 §4. Meritz 는 외화 자동 RP 로 현금 파킹이 자동 |
| 현금 파킹 | 대기 현금을 증권사 RP(2~3%) 또는 단기채 ETF 에 | 수익 +2~3%p, 낙폭 불변. GLD 와 보완 관계(docs/02 §2.2). Meritz 자동 RP 면 `cash_yield_annual: 0.03, cash_yield_fraction: 1.0`, KIS 수동이면 0.8 |

## 2. 최초 1회 설정

```bash
uv venv && uv pip install -e ".[data,dev]"        # 설치 (Windows 도 동일, README)
uv run qtrade data update                          # SOXL, SOXX, USDKRW (+ GLD 는 아래)
uv run qtrade data update GLD
uv run qtrade backtest -c configs/soxl_balanced.yaml -o reports/live   # 최신 데이터로 프로필 확인
```

운용 설정 파일 만들기: `configs/soxl_balanced.yaml` 을 복사해 `configs/live_soxl.yaml` 로 두고 두 값만 바꾼다.
- `initial_capital`: 바스켓 슬리브에 배정한 달러 금액 (전략 B 면 계좌의 70%)
- `data.start`: 운용 시작일 (이 날부터 replay 가 시작된다. 지표 워밍업은 그 이전 데이터를 자동으로 씀)

포트폴리오 파일 `configs/portfolio_soxl_gld.yaml` 의 `initial_capital` 을 계좌 총액으로, 슬리브 config 를 `configs/live_soxl.yaml` 로 바꾼다.
`configs/*.yaml` 은 `qtrade make-configs` 가 덮어쓰므로 **운용 파일은 `live_` 접두어로 따로 둔다.**

## 3. 매일 루틴 (한국시간 아침, 미국 장 마감 후)

```bash
uv run qtrade data update
uv run qtrade portfolio configs/portfolio_soxl_gld.yaml          # 통합 주문서 → reports/portfolio/portfolio_soxl_gld_orders.csv
# 바스켓 단독 운용이면:
uv run qtrade orders -c configs/live_soxl.yaml -o reports/orders --env real --format kis   # 또는 --format meritz
```

집행기가 HTTP 로 받아가게 하려면 `uv run qtrade serve --host 0.0.0.0 --port 8787 --token <비밀> --update` 를 띄워 둔다(docs/05 §2).

주문표 읽는 법:
- `BUY LOC 지정가`: 종가가 지정가 이하로 마감하면 체결. 같은 가격의 바스켓 주문은 한 건으로 합쳐져 있다.
- `SELL LOC 지정가`: 로트 익절. 종가가 지정가 이상이면 체결. 지정가가 전일종가와 같은 `upday_sell` 은 상승 마감일 부분매도.
- `SELL MOC`: 바스켓 전량 청산(목표 도달·기간 만료·약세 전환). 반드시 낸다.
- `GLD BUY/SELL MOC rebalance→30%`: 연 1회 슬리브 리밸런싱(§4). `SOXL RESET CAPITAL`: 주문이 아니라 설정 재설정 안내 행이다 — 집행기에 보내지 않는다.
- 같은 날 매수·매도가 동시에 나오는 것이 정상이다. 서로 다른 가격이므로 둘 다 낸다.
- 첫 줄에 `⚠ 데이터가 오래됨` 이 보이면 갱신 실패다. 그 주문표는 쓰지 않는다.

## 4. 월·분기·연 루틴

| 주기 | 할 일 |
|---|---|
| 월 1회 | `qtrade portfolio configs/portfolio_soxl_gld.yaml` 리포트로 슬리브별·결합 성과와 낙폭 확인. 집행기 잔고와 replay 상태(`state_*.csv`) 대조 — 수량·평단 차이 1% 초과면 §6 재설정 |
| 분기 1회 | 스냅샷 커밋(`git add -f data/cache/*.csv`), `qtrade walkforward -c configs/soxl_balanced_cache.yaml -g configs/sweeps/walkforward_core.yaml` 재실행. 선정 조합이 프로필과 달라지면 docs/02 §3 에 기록하고 `profiles.py` 변경을 검토 |
| 연 1회 (전년 마지막 거래일 아침 발급분) | 통합 주문서에 `GLD BUY/SELL MOC rebalance→30%` 와 `SOXL RESET CAPITAL <금액>` 행이 나온다. GLD 주문은 그대로 집행하고, RESET 행의 금액을 `configs/live_soxl.yaml` 의 `initial_capital` 에 넣고 `data.start` 를 새해 첫 거래일로 바꾼다(보유 SOXL 이 있으면 §6 (a)/(b) 중 택일). `qtrade tax` 로 전년도 양도세 산출액을 확인해 5월 납부 현금을 남긴다 |

## 5. 이상 상황 대응

| 상황 | 대응 |
|---|---|
| 낙폭이 프로필 MDD(균형형 −28%, 전략 B −19%)를 넘음 | 규칙을 바꾸지 말고 **멈춘다.** 데이터 오류·체결 오차·시장 구조 변화를 백테스트로 확인한 뒤에만 재개 |
| `regime_bear` MOC 청산이 나옴 | 건너뛰지 않는다. 2008·2022 에서 계좌를 지킨 규칙이다 |
| 공격형에서 `⚠ 서킷브레이커 발동 중` | 매수 주문이 없는 것이 정상. SOXL 이 200일선 위로 복귀하면 자동 재개 |
| 미체결·부분체결로 replay 와 실계좌가 어긋남 | 소액이면 무시(월 대조에서 1% 이내). 넘으면 §6 |
| 입출금 | §6 재설정 |
| yfinance 오류로 갱신 실패 | 그날은 주문 없이 넘긴다. 이틀 이상이면 `data/cache/*.csv` 를 다른 소스로 채운 뒤 재발급 |
| 현금 비중 80% 이상 | 정상이다. 그 현금이 낙폭을 −28% 로 만든 장본인이다. 단기채 파킹 외 다른 종목 매수 금지 |

## 6. 재설정 (새 라운드 시작)

replay 와 실계좌가 어긋났거나 입출금이 있었을 때: `configs/live_soxl.yaml` 의 `data.start` 를 오늘로, `initial_capital` 을 바스켓 슬리브의 현재 달러 총액으로 바꾼다. 보유 SOXL 이 있으면 (a) 전량 MOC 매도 후 새 라운드를 시작하거나, (b) 보유분을 그대로 두고 현금만 재설정한다(이 경우 보유분은 수동 관리). 단순한 (a) 를 권한다.

## 7. 운용자 심리 규칙

1. 주문표를 그대로 넣는다. 종가 주문이라 장중 가격을 볼 이유가 없다. 하루 한 번, 정해진 시간에만.
2. 낙폭은 설계된 값이다. 균형형은 백테스트 기간의 16% 를 낙폭 20% 초과 상태로 보냈다. 이상 신호는 "프로필 MDD 를 넘는 낙폭"뿐.
3. 낙폭 뒤 규모 축소는 회복을 4배 늦췄다(검증됨). 프로필은 시작 전에 고르고 낙폭 중에 바꾸지 않는다.
4. 강세장에서 SOXL 보유보다 덜 버는 것은 설계다. 투자비중 16% 가 낙폭 −28% 를 만든다.
5. 월 1회만 성과를 본다.

## 8. 바꾸지 않는 것

강제 시간청산(`hard_max_hold_days`), 약세 전환 청산(`bear_liquidate`), 상승일 부분매도(`upday_sell_frac`, 0 이면 MDD −45%), 손절 없음(`basket_sl_pct: null`), 약세장 바스켓 1개. 근거 docs/02 §3.
