# 05. 집행기 연동 (KIS auto_trade / Meritz rpa_claude)

전략 엔진(quant_trading)은 **주문서만 발급**하고, 실제 주문은 두 집행기 중 하나가 낸다. 연동 계약은 파일 형식 두 가지와 HTTP 엔드포인트 하나다.

## 1. 주문서 형식

| 집행기 | 형식 | 생성 | 규격 출처 |
|---|---|---|---|
| KIS `auto_trade` | JSON `orders_{env}_SOXL_{profile}_{date}.json` | `qtrade orders ... --format kis --env paper\|real` | auto_trade `docs/order-sheet-spec.md` v1 |
| Meritz `rpa_claude` | CSV `orders_meritz_SOXL_{profile}_{date}.csv` (컬럼 side,symbol,quantity,price,order_type,memo) | `qtrade orders ... --format meritz` | rpa_claude README "주문 CSV 형식" |

- 두 형식 모두 **같은 (매수/매도, 유형, 지정가) 주문을 한 건으로 합친다**(바스켓 4개가 같은 가격에 사는 경우). memo/tag 에 바스켓 번호가 남는다.
- 매도가 먼저, 매수가 뒤에 온다(현금 확보 순).
- `LOC` 지정가는 소수 2자리. `MOC` 는 KIS 는 `ref_price` 에 종가를 참고로 넣고, Meritz 는 price 를 비운다(needs_price=false).
- KIS 모의투자는 LOC/MOC 를 지정가로 자동 대체한다(auto_trade 집행기). Meritz 는 LOC/MOC 유형이 config 에 등록돼 있다.

## 2. 발급 방법 두 가지

**명령 실행** (집행기 스케줄러가 셸로 호출):

```bash
uv run qtrade data update
uv run qtrade orders -c configs/soxl_balanced.yaml -o reports/orders --format meritz
uv run qtrade orders -c configs/soxl_balanced.yaml -o reports/orders --format kis --env paper
```

**HTTP 요청** (엔진을 상주시키고 집행기가 GET):

```bash
uv run qtrade serve --host 0.0.0.0 --port 8787 --token SECRET --update     # 전략 PC
curl -H "X-Token: SECRET" "http://strategy-pc:8787/orders?profile=balanced&format=meritz&refresh=1" -o orders/orders.csv
curl -H "X-Token: SECRET" "http://strategy-pc:8787/orders?profile=balanced&format=kis&env=real" -o results/orders/sheet.json
curl -H "X-Token: SECRET" "http://strategy-pc:8787/health?profile=balanced"   # {"ok":true,"last_close":"2026-09-18","stale_days":0}
```

- `refresh=1` 은 yfinance 로 시세를 갱신한 뒤 발급한다(`--update` 없이도 동작). `capital=`, `start=` 로 운용자본·시작일을 요청마다 덮어쓸 수 있다.
- 발급 파일은 서버의 `--out` 에도 저장된다. 같은 (profile, 기준일) 요청은 캐시된다.
- **LAN 전용**이다. 토큰은 공유 비밀일 뿐 TLS 가 없으므로 공개망에 노출하지 않는다.
- 미완성 당일 봉은 갱신 시 걸러지므로, 미국 장 마감(동부 16:10) 전에는 전일 종가 기준 주문서가 나온다. 이것이 의도한 동작이다.

## 3. 일일 스케줄 (한국시간, 서머타임 기준)

| 시각 (KST) | 주체 | 동작 |
|---|---|---|
| 05:00 | 미국 정규장 마감 | |
| 06:30~07:00 | 전략 엔진 | `data update` → 주문서 발급 (또는 집행기의 `refresh=1` 요청) |
| 17:00~18:00 | 집행기 | 주문서 수신·검증. rpa_claude 는 18:05 "전략 Trade" 슬롯, auto_trade 는 `order execute` |
| 18:00~22:30 | 프리마켓 | LOC 는 정규장 마감 체결이라 이 시간에 접수해도 무방. KIS 실전은 프리마켓 접수 실측됨 |
| 22:30 | 정규장 개장 | |
| 05:00 (익일) | 정규장 마감 | LOC/MOC 체결 → 다음 날 아침 사이클 |

주문서의 `trade_date` 는 "마지막 종가일" 이고, 주문은 **그 다음 거래일** 종가에 체결되는 것을 전제로 한다. 발급 후 하루가 지나면(휴장 제외) 폐기하고 새로 발급한다.

## 4. KIS vs Meritz 선택 기준 (아직 미결정)

| 항목 | KIS auto_trade (API) | Meritz rpa_claude (RPA) | 비고 |
|---|---|---|---|
| 접수 정확도 | 응답 코드로 즉시 확인, 주문번호 보관 | 확인창 닫힘·되읽기 검증. 화면·글꼴 의존 | RPA 는 HTS 업데이트 시 재측정 필요 |
| 안정성 | 토큰 만료·유량 제한(EGW00201) 관리 필요 | HTS 로그인 상태·팝업·해상도 의존 | 둘 다 실운용 중이므로 grid 로그로 실측 가능 |
| 외화 유휴현금 | 원화 RP 는 있으나 외화 자동 RP 미확인 | 원화·외화 예수금 자동 RP 매수, 거래 시 자동 매도 | 현금 파킹 가정(docs/02 §2.1)을 **Meritz 는 자동으로 충족**, KIS 는 SGOV/BIL 수동 매매 필요 |
| 모의투자 | 있음(지정가만) | 없음 → `dry_run` | 페이퍼 트레이딩 방식이 달라짐 (§5) |
| 수수료·환전 | 실측 필요 | 실측 필요 | 미확인 값을 문서에 적지 않는다. 각 집행기의 체결 기록으로 편도 비용을 계산해 `costs.commission_pct` 에 반영 |

권장: 두 집행기가 **같은 주문서**를 받을 수 있으므로, 한쪽은 실계좌·한쪽은 모의/dry_run 으로 30거래일 병행해 접수 성공률·체결가 오차·유휴현금 수익을 비교한 뒤 정한다.

## 5. 페이퍼 트레이딩의 두 층위

1. **시뮬레이션 발급 기록** (주문 없음): 매일 주문서를 발급해 보관만 하고, 다음 날 실제 종가로 "체결됐을 것"을 엔진이 재현한다. 지금의 백테스트 replay 와 같으며 새 정보는 "주문서 발급 절차가 매일 돌아가는가" 뿐이다.
2. **모의 집행** (실제 주문, 가상 계좌): KIS 모의투자 계좌에 auto_trade 로 실제 접수한다. 접수 거부·미체결·체결가 차이가 실측된다. 단, 모의투자는 LOC 가 지정가로 대체되므로 LOC 체결 정합성은 실계좌 소액으로만 검증된다. Meritz 는 모의 계좌가 없어 `dry_run`(입력까지만) 이 상한이다.

권장 순서: 1 을 1주(스케줄 검증) → 2 를 30거래일(KIS 모의) → 실계좌 소액(양쪽) 으로 LOC 접수 실측 → 집행기 확정.
