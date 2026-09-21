# 실험·기각 설정 (재현용)

docs/07 §4 의 기각·보류 검증을 재현하기 위한 설정. 실운용·권장 구성과 무관하다.

| 파일 | 검증 | 결과 |
|---|---|---|
| tqqq/upro/tecl_balanced_cache.yaml | 균형형 규칙을 다른 3배 ETF 에 적용 | 기각 (SOXL 열위, 상관 0.6~0.86) — §4.2 |
| kodex_lev_*_cache.yaml | 국내 KODEX 레버리지 | 기각 (저변동 박스권) — §4.8 |
| ief_always.yaml, shy_always.yaml, bear_tlt.yaml, bear_gld.yaml | 채권·국면별 GLD 슬리브 | 보류/기각 — §4.3, §4.4 |

추세추종(trend)·v5 변동성 수확(v5_scalp) kind 는 코드째 제거했다(§4.1, §4.6). 결과 CSV 는 `reports/sweeps/trend1.csv`, `reports/portfolio/combos_v5.csv`.
