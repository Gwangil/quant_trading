# CLAUDE.md — 개발 규칙 (AI 에이전트·사람 공통)

## 프로젝트가 하는 일
레버리지 ETF 전략(분할 바스켓 LOC, 추세추종 등)의 **개발·검증·주문서 발급**. 실제 주문·체결 대사·스케줄 실행은 하지 않는다
(집행기 auto_trade(KIS API) / rpa_claude(Meritz RPA) 가 주문서 파일을 받아서 한다 — docs/05, 역할 경계 docs/07 §1).
성과 판단은 세전 달러 기준.

## 시작할 때 읽을 것
1. `docs/04_roadmap.md` — 진행 상태·열린 과제
2. `docs/02_backtest_results.md` §3 — 이미 검증되어 뒤집지 않을 결론
3. `docs/06_config_reference.md` — 옵션 목록과 채택/기각 상태

## 불변 규칙
- **파라미터는 `src/qtrade/profiles.py` 한 곳에서만** 바꾸고 `qtrade make-configs` 로 YAML 을 재생성한다. `configs/*.yaml` 직접 수정 금지.
- 엔진 기본값(`config.py`) 은 균형형 프로필과 같아야 한다 (`test_engine_defaults_match_balanced_profile`).
- `config.py` 를 바꾸면 `python scripts/gen_config_reference.py` 로 docs/06 을 재생성한다.
- 파라미터 변경은 근거(스윕/워크포워드 결과, IS/OOS)와 함께 docs/02 §3 표에 한 줄 추가한다. OOS(2018~)를 보고 고르지 않는다.
- 주 검증 데이터는 `data/cache/SOXL.csv`, `SOXX.csv`(git 추적). 갱신은 `qtrade data update` 후 커밋. `data/bundled/` 는 기준 전략 동등성 테스트용이라 수정하지 않는다.
- 미래참조 금지: 당일 종가 판단은 당일 종가까지의 정보만. 주문은 다음 거래일 종가 체결(LOC/MOC).
- 집행기 주문서 형식(KIS JSON v1, Meritz CSV)은 집행기 저장소의 규격이 정답이다. 바꾸려면 그쪽 문서를 먼저 확인.
- `qtrade serve` 는 LAN 전용. 인증은 공유 토큰뿐이다.
- 새 전략은 `src/qtrade/strategies/` 에 kind 로 등록하고(docs/07 §2), 채택 기준은 바스켓과 동일(IS/OOS, 이웃 절벽 없음, 기존 슬리브와 상관 < 0.5).
- 커밋 전 `pytest -q` 통과. 리포트(`reports/`)는 결과 문서의 근거이므로 재생성 후 함께 커밋.

## 자주 쓰는 명령
```bash
uv run pytest -q
uv run qtrade data update
uv run qtrade backtest -c configs/soxl_balanced.yaml -o reports/live
uv run qtrade orders -c configs/soxl_balanced.yaml -o reports/orders --env paper
uv run qtrade compare            # 기준 전략(baseline/v5) 대비
uv run qtrade tax -c configs/soxl_balanced.yaml   # 세후 원화 (참고용)
uv run qtrade portfolio configs/portfolio_soxl_gld.yaml  # 권장 다전략(바스켓 70 + GLD 30) + 통합 주문서
uv run qtrade walkforward -c configs/soxl_balanced_cache.yaml -g configs/sweeps/walkforward_core.yaml
uv run qtrade make-configs && python scripts/gen_config_reference.py
```

## 폴더
`src/qtrade/` 패키지 · `configs/` 생성된 설정(+`sweeps/` 그리드) · `data/` 시세 · `reports/` 결과 · `docs/` 문서 · `scripts/` 보조 스크립트 · `tests/`
