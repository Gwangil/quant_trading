# 빠른 시작 가이드 (Quick Start Guide)

## 최소 요구사항

- Docker & Docker Compose
- 8GB RAM 이상
- 20GB 디스크 공간
- 인터넷 연결 (데이터 수집용)

## 5분 안에 시작하기

### 1단계: 프로젝트 클론

```bash
git clone <repository-url>
cd quant_trading
```

### 2단계: 환경 설정

```bash
# 환경 변수 파일 복사
cp .env.example .env

# 필수 설정만 수정 (.env 파일)
# 아래 3개만 설정하면 바로 시작 가능
POSTGRES_PASSWORD=your_secure_password
TIMESCALE_PASSWORD=your_secure_password
RABBITMQ_PASSWORD=your_secure_password
```

### 3단계: 시스템 시작

```bash
# 전체 시스템 시작 (첫 실행시 5-10분 소요)
docker-compose up -d

# 상태 확인
docker-compose ps
```

### 4단계: 대시보드 접속

```
http://localhost:3000
```

## 첫 백테스트 실행

### 간단한 모멘텀 전략 테스트

```bash
curl -X POST http://localhost:8001/backtest \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_name": "momentum",
    "symbols": ["SPY", "QQQ"],
    "start_date": "2023-01-01",
    "end_date": "2023-12-31",
    "initial_capital": 100000
  }'
```

### 결과 확인

```bash
# 백테스트 ID를 받은 후
curl http://localhost:8001/backtest/{backtest_id}
```

## 포트폴리오 선택하여 실행

### 옵션 1: 보수적 포트폴리오

```bash
# .env 파일 수정
ACTIVE_PORTFOLIOS=Conservative Portfolio
PORTFOLIO_CAPITAL_ALLOCATION=1.0

# 재시작
docker-compose restart strategy_engine
```

### 옵션 2: 균형 포트폴리오

```bash
# .env 파일 수정
ACTIVE_PORTFOLIOS=Balanced Portfolio
PORTFOLIO_CAPITAL_ALLOCATION=1.0

# 재시작
docker-compose restart strategy_engine
```

### 옵션 3: 공격적 포트폴리오

```bash
# .env 파일 수정
ACTIVE_PORTFOLIOS=Aggressive Portfolio
PORTFOLIO_CAPITAL_ALLOCATION=1.0

# 재시작
docker-compose restart strategy_engine
```

## API 키 설정 (선택사항)

더 안정적인 데이터를 위해 API 키 추가:

### 무료 API 키 획득

1. **Alpha Vantage** (무료)
   - https://www.alphavantage.co/support/#api-key
   - 분당 5회, 일일 500회 제한

2. **Polygon.io** (무료 플랜 있음)
   - https://polygon.io
   - 더 나은 데이터 품질

### API 키 설정

```bash
# .env 파일에 추가
ALPHA_VANTAGE_API_KEY=your_api_key_here
POLYGON_API_KEY=your_api_key_here
```

## 일일 주문 생성

### 오늘의 주문 확인

```bash
curl http://localhost:8000/orders/today
```

### 수동으로 주문 생성

```bash
curl -X POST http://localhost:8000/orders/generate
```

## 모니터링

### 시스템 상태 확인

```bash
# 전체 서비스 상태
curl http://localhost:8000/health

# 포트폴리오 현황
curl http://localhost:8000/portfolio

# 실시간 로그 확인
docker-compose logs -f strategy_engine
```

### 성과 확인

```bash
# 일일 성과
curl http://localhost:8000/portfolio/performance/daily

# 전략별 성과
curl http://localhost:8000/strategies/performance
```

## 문제 해결

### 서비스가 시작되지 않을 때

```bash
# 로그 확인
docker-compose logs [service_name]

# 개별 서비스 재시작
docker-compose restart [service_name]

# 전체 재시작
docker-compose down
docker-compose up -d
```

### 데이터가 없을 때

```bash
# 수동 데이터 수집
docker-compose exec data_collector python -c "
from src.main import DataCollectorService
service = DataCollectorService()
service.run_daily_collection()
"
```

### 메모리 부족

```bash
# Docker 메모리 할당 증가 (Docker Desktop 설정)
# 또는 docker-compose.yml에서 제한 설정

services:
  strategy_engine:
    mem_limit: 2g
```

## 다음 단계

1. **상세 문서 읽기**
   - [개발 가이드](01-development-guide.md)
   - [운영 가이드](02-operation-guide.md)
   - [전략 가이드](03-strategy-guide.md)

2. **커스텀 전략 추가**
   - `/services/strategy_engine/src/strategies/` 폴더에 새 전략 파일 생성

3. **백테스트 최적화**
   - 다양한 기간과 파라미터로 테스트
   - 여러 전략 조합 실험

4. **실전 거래 준비**
   - Paper Trading으로 충분히 테스트
   - 리스크 관리 설정 확인
   - 실제 브로커 API 연동

## 자주 묻는 질문

**Q: 최소한의 설정으로 바로 시작할 수 있나요?**
A: 네, .env.example을 .env로 복사하고 패스워드만 설정하면 바로 시작 가능합니다.

**Q: API 키가 없어도 작동하나요?**
A: 네, Yahoo Finance를 기본으로 사용합니다. 단, API 키가 있으면 더 안정적입니다.

**Q: 실제 돈으로 거래가 되나요?**
A: 아니요, 기본 설정은 시뮬레이션입니다. 실거래는 브로커 API 연동이 필요합니다.

**Q: 어떤 ETF를 거래하나요?**
A: 기본적으로 미국 주요 ETF (SPY, QQQ, IWM 등)를 거래합니다.

**Q: 백테스트는 얼마나 걸리나요?**
A: 1년 데이터 기준 약 1-2분, 3년 데이터는 5-10분 정도 소요됩니다.