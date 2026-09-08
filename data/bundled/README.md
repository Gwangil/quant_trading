# 번들 데이터

| 파일 | 내용 | 출처 |
|---|---|---|
| NASDAQ.csv, SP500.csv | 지수 일봉 1999-01 ~ 2018-12 | arch 패키지 번들 |
| SOXL.csv | SOXL 종가·RSI(14) 2001-08 ~ 2026-07-24. 2010-03-11 이전은 SOXX 일수익률×3 역산 합성 | Gwangil/invest_strategy 스냅샷 (yfinance) |
| SOXX.csv | 기준지수용. Close = SOXX (High+Low)/2 근사, Open/High/Low/Volume 은 SOXX 원값 | 동일 스냅샷 |

SOXX 스냅샷에는 종가 컬럼이 없어 고가·저가 중간값을 종가 대용으로 쓴다(200일선 레짐 판단용이라 영향 미미).
| reference_equity_cap1e8.csv | 원본 invest_strategy 코드로 baseline/v5 를 자본 1억으로 실행한 일별 총자산 (동등성 테스트 기준값) | 원본 코드 실행 |
