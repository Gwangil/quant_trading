# 운영 가이드 (Operation Guide)

## 목차
1. [시스템 시작 및 종료](#시스템-시작-및-종료)
2. [일일 운영 체크리스트](#일일-운영-체크리스트)
3. [모니터링](#모니터링)
4. [데이터 관리](#데이터-관리)
5. [백업 및 복구](#백업-및-복구)
6. [트러블슈팅](#트러블슈팅)
7. [성능 최적화](#성능-최적화)

## 시스템 시작 및 종료

### 전체 시스템 시작

```bash
# 1. 환경 변수 확인
cat .env | grep -E "ENVIRONMENT|DATABASE|API_KEY"

# 2. 데이터베이스 먼저 시작
docker-compose up -d postgres timescaledb redis

# 3. 데이터베이스 상태 확인 (30초 대기)
sleep 30
docker-compose ps postgres timescaledb redis

# 4. 메시지 큐 시작
docker-compose up -d rabbitmq

# 5. 마이크로서비스 시작
docker-compose up -d data_collector strategy_engine backtesting order_generator

# 6. API 및 UI 시작
docker-compose up -d api_gateway admin_ui

# 7. 전체 상태 확인
docker-compose ps
curl http://localhost:8000/health
```

### 안전한 시스템 종료

```bash
# 1. 실행 중인 거래 확인
curl http://localhost:8000/orders/pending

# 2. 거래 중지
curl -X POST http://localhost:8000/trading/stop

# 3. 데이터 저장 확인
docker-compose exec strategy_engine python -c "
from src.portfolio_manager import PortfolioManager
pm = PortfolioManager()
pm.save_portfolio_state()
"

# 4. 서비스 순차 종료
docker-compose stop admin_ui api_gateway
docker-compose stop order_generator backtesting strategy_engine data_collector
docker-compose stop rabbitmq redis
docker-compose stop timescaledb postgres
```

## 일일 운영 체크리스트

### 오전 점검 (시장 개장 전)

```bash
#!/bin/bash
# daily_morning_check.sh

echo "=== 오전 시스템 점검 시작 ==="

# 1. 시스템 상태 확인
echo "1. 시스템 상태 확인"
docker-compose ps

# 2. 데이터베이스 연결 확인
echo "2. 데이터베이스 상태"
docker-compose exec postgres pg_isready
docker-compose exec timescaledb psql -U timescale_user -d market_data -c "SELECT COUNT(*) FROM market_data WHERE date = CURRENT_DATE;"

# 3. 어제 데이터 수집 확인
echo "3. 데이터 수집 상태"
docker-compose logs --tail=100 data_collector | grep ERROR

# 4. 전략 엔진 상태
echo "4. 전략 엔진 상태"
curl http://localhost:8000/strategies/status

# 5. 디스크 공간 확인
echo "5. 디스크 공간"
df -h | grep -E "Filesystem|docker"

# 6. 메모리 사용량
echo "6. 메모리 사용량"
docker stats --no-stream

echo "=== 점검 완료 ==="
```

### 시장 시간 중 모니터링

```python
# monitoring/real_time_monitor.py

import time
import requests
from datetime import datetime

class RealTimeMonitor:
    def __init__(self):
        self.api_base = "http://localhost:8000"
        self.alert_threshold = {
            'portfolio_drawdown': -0.05,  # 5% 손실
            'daily_loss': -0.03,          # 3% 일일 손실
            'error_rate': 0.1              # 10% 에러율
        }

    def check_portfolio_health(self):
        """포트폴리오 상태 확인"""
        response = requests.get(f"{self.api_base}/portfolio")
        data = response.json()

        current_value = data['current_value']
        initial_value = data['initial_value']
        drawdown = (current_value - initial_value) / initial_value

        if drawdown < self.alert_threshold['portfolio_drawdown']:
            self.send_alert(f"포트폴리오 손실 경고: {drawdown:.2%}")

        return data

    def check_strategy_performance(self):
        """전략별 성과 확인"""
        response = requests.get(f"{self.api_base}/strategies/performance")
        strategies = response.json()

        for strategy in strategies:
            if strategy['daily_return'] < self.alert_threshold['daily_loss']:
                self.send_alert(f"전략 {strategy['name']} 일일 손실: {strategy['daily_return']:.2%}")

    def check_system_errors(self):
        """시스템 에러 확인"""
        response = requests.get(f"{self.api_base}/system/errors")
        error_stats = response.json()

        error_rate = error_stats['error_count'] / error_stats['total_requests']
        if error_rate > self.alert_threshold['error_rate']:
            self.send_alert(f"시스템 에러율 증가: {error_rate:.2%}")

    def send_alert(self, message):
        """알림 발송"""
        print(f"[ALERT] {datetime.now()}: {message}")
        # Slack, Email 등 알림 발송 로직

    def run_monitoring(self):
        """실시간 모니터링 실행"""
        while True:
            try:
                self.check_portfolio_health()
                self.check_strategy_performance()
                self.check_system_errors()
            except Exception as e:
                print(f"모니터링 에러: {e}")

            time.sleep(60)  # 1분마다 확인

if __name__ == "__main__":
    monitor = RealTimeMonitor()
    monitor.run_monitoring()
```

### 오후 점검 (시장 마감 후)

```bash
#!/bin/bash
# daily_evening_check.sh

echo "=== 오후 정산 시작 ==="

# 1. 오늘 거래 내역 수집
echo "1. 거래 내역 수집"
curl http://localhost:8000/orders/today > reports/trades_$(date +%Y%m%d).json

# 2. 포트폴리오 성과 계산
echo "2. 성과 계산"
curl http://localhost:8000/portfolio/performance > reports/performance_$(date +%Y%m%d).json

# 3. 내일 주문 생성
echo "3. 내일 주문 준비"
curl -X POST http://localhost:8000/orders/generate

# 4. 백업 실행
echo "4. 데이터 백업"
./scripts/backup.sh

# 5. 로그 정리
echo "5. 로그 정리"
find /var/log/quant_trading -name "*.log" -mtime +7 -delete

echo "=== 정산 완료 ==="
```

## 모니터링

### Prometheus 설정

```yaml
# prometheus/prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'quant_trading'
    static_configs:
      - targets:
        - 'api_gateway:8000'
        - 'strategy_engine:9090'
        - 'data_collector:9091'
        - 'backtesting:9092'

  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres_exporter:9187']

  - job_name: 'redis'
    static_configs:
      - targets: ['redis_exporter:9121']
```

### Grafana 대시보드

```json
{
  "dashboard": {
    "title": "Quant Trading System",
    "panels": [
      {
        "title": "Portfolio Value",
        "targets": [
          {
            "expr": "portfolio_total_value"
          }
        ]
      },
      {
        "title": "Daily Returns",
        "targets": [
          {
            "expr": "rate(portfolio_returns[1d])"
          }
        ]
      },
      {
        "title": "Strategy Performance",
        "targets": [
          {
            "expr": "strategy_performance_by_name"
          }
        ]
      },
      {
        "title": "System Health",
        "targets": [
          {
            "expr": "up"
          }
        ]
      }
    ]
  }
}
```

### 알림 규칙

```yaml
# alertmanager/alerts.yml
groups:
  - name: trading_alerts
    rules:
      - alert: HighDrawdown
        expr: (portfolio_value - portfolio_peak_value) / portfolio_peak_value < -0.1
        for: 5m
        annotations:
          summary: "포트폴리오 10% 이상 손실"

      - alert: DataCollectionFailed
        expr: up{job="data_collector"} == 0
        for: 10m
        annotations:
          summary: "데이터 수집 서비스 다운"

      - alert: HighMemoryUsage
        expr: container_memory_usage_bytes / container_spec_memory_limit_bytes > 0.9
        for: 5m
        annotations:
          summary: "메모리 사용량 90% 초과"
```

## 데이터 관리

### 데이터 수집 스케줄

```python
# schedulers/data_scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
import logging

class DataScheduler:
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.logger = logging.getLogger(__name__)

    def setup_schedules(self):
        """데이터 수집 스케줄 설정"""

        # 일일 데이터 수집 (매일 오후 6시)
        self.scheduler.add_job(
            self.collect_daily_data,
            'cron',
            hour=18,
            minute=0,
            id='daily_collection'
        )

        # 실시간 데이터 수집 (시장 시간 중 1분마다)
        self.scheduler.add_job(
            self.collect_realtime_data,
            'cron',
            day_of_week='mon-fri',
            hour='9-16',
            minute='*',
            id='realtime_collection'
        )

        # 주간 데이터 정리 (일요일 자정)
        self.scheduler.add_job(
            self.cleanup_old_data,
            'cron',
            day_of_week='sun',
            hour=0,
            minute=0,
            id='weekly_cleanup'
        )

    def collect_daily_data(self):
        """일일 데이터 수집"""
        self.logger.info("일일 데이터 수집 시작")
        # 수집 로직

    def collect_realtime_data(self):
        """실시간 데이터 수집"""
        # 실시간 수집 로직
        pass

    def cleanup_old_data(self):
        """오래된 데이터 정리"""
        self.logger.info("데이터 정리 시작")
        # 30일 이상 된 분 단위 데이터 시간 단위로 집계
        # 1년 이상 된 시간 단위 데이터 일 단위로 집계
```

### 데이터 검증

```python
# validators/data_validator.py
import pandas as pd
from typing import Optional

class DataValidator:
    @staticmethod
    def validate_ohlcv(df: pd.DataFrame) -> tuple[bool, Optional[str]]:
        """OHLCV 데이터 검증"""

        # 필수 컬럼 확인
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        if not all(col in df.columns for col in required_columns):
            return False, "필수 컬럼 누락"

        # 가격 논리 확인
        if (df['high'] < df['low']).any():
            return False, "High < Low 데이터 존재"

        if (df['high'] < df['close']).any() or (df['high'] < df['open']).any():
            return False, "High 값이 잘못됨"

        if (df['low'] > df['close']).any() or (df['low'] > df['open']).any():
            return False, "Low 값이 잘못됨"

        # 볼륨 확인
        if (df['volume'] < 0).any():
            return False, "음수 볼륨 존재"

        # 결측치 확인
        if df[required_columns].isnull().any().any():
            return False, "결측치 존재"

        return True, None
```

## 백업 및 복구

### 자동 백업 스크립트

```bash
#!/bin/bash
# scripts/backup.sh

BACKUP_DIR="/backup/quant_trading"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=30

echo "백업 시작: $DATE"

# 1. PostgreSQL 백업
docker-compose exec -T postgres pg_dump -U postgres quant_trading | gzip > $BACKUP_DIR/postgres_$DATE.sql.gz

# 2. TimescaleDB 백업
docker-compose exec -T timescaledb pg_dump -U timescale_user market_data | gzip > $BACKUP_DIR/timescale_$DATE.sql.gz

# 3. Redis 백업
docker-compose exec -T redis redis-cli BGSAVE
docker cp redis:/data/dump.rdb $BACKUP_DIR/redis_$DATE.rdb

# 4. 설정 파일 백업
tar -czf $BACKUP_DIR/config_$DATE.tar.gz .env docker-compose.yml services/*/config.py

# 5. 오래된 백업 삭제
find $BACKUP_DIR -type f -mtime +$RETENTION_DAYS -delete

echo "백업 완료: $DATE"
```

### 복구 절차

```bash
#!/bin/bash
# scripts/restore.sh

if [ $# -ne 1 ]; then
    echo "Usage: ./restore.sh YYYYMMDD_HHMMSS"
    exit 1
fi

BACKUP_DATE=$1
BACKUP_DIR="/backup/quant_trading"

echo "복구 시작: $BACKUP_DATE"

# 1. 서비스 중지
docker-compose down

# 2. PostgreSQL 복구
docker-compose up -d postgres
sleep 10
gunzip -c $BACKUP_DIR/postgres_$BACKUP_DATE.sql.gz | docker-compose exec -T postgres psql -U postgres

# 3. TimescaleDB 복구
docker-compose up -d timescaledb
sleep 10
gunzip -c $BACKUP_DIR/timescale_$BACKUP_DATE.sql.gz | docker-compose exec -T timescaledb psql -U timescale_user

# 4. Redis 복구
docker cp $BACKUP_DIR/redis_$BACKUP_DATE.rdb redis:/data/dump.rdb
docker-compose restart redis

# 5. 설정 복구
tar -xzf $BACKUP_DIR/config_$BACKUP_DATE.tar.gz

# 6. 서비스 재시작
docker-compose up -d

echo "복구 완료"
```

## 트러블슈팅

### 일반적인 문제 해결

#### 1. 데이터 수집 실패

```bash
# 증상: 데이터가 업데이트되지 않음

# 진단
docker-compose logs --tail=100 data_collector | grep ERROR
docker-compose exec data_collector curl -I https://api.polygon.io/v2/aggs/ticker/SPY/range/1/day/2023-01-01/2023-01-01

# 해결
# 1. API 키 확인
grep API_KEY .env

# 2. 네트워크 확인
docker-compose exec data_collector ping -c 3 8.8.8.8

# 3. 서비스 재시작
docker-compose restart data_collector

# 4. 수동 수집 실행
docker-compose exec data_collector python -c "
from src.main import DataCollectorService
service = DataCollectorService()
service.collect_symbol('SPY', '2024-01-01', '2024-01-31')
"
```

#### 2. 메모리 부족

```bash
# 증상: 서비스가 자주 재시작됨

# 진단
docker stats --no-stream
dmesg | grep -i "killed process"

# 해결
# 1. 메모리 제한 조정 (docker-compose.yml)
# services:
#   strategy_engine:
#     mem_limit: 2g
#     mem_reservation: 1g

# 2. 불필요한 데이터 정리
docker-compose exec timescaledb psql -U timescale_user -d market_data -c "
DELETE FROM market_data WHERE date < NOW() - INTERVAL '2 years';
"

# 3. 캐시 정리
docker-compose exec redis redis-cli FLUSHDB
```

#### 3. 전략 실행 오류

```python
# 증상: 전략이 신호를 생성하지 않음

# debug_strategy.py
import sys
sys.path.append('/app')

from services.strategy_engine.src.strategies.momentum import MomentumStrategy
from services.data_collector.src.database import get_market_data
import logging

logging.basicConfig(level=logging.DEBUG)

# 데이터 로드
data = get_market_data(['SPY'], '2024-01-01', '2024-01-31')
print(f"데이터 shape: {data.shape}")
print(f"데이터 컬럼: {data.columns.tolist()}")

# 전략 실행
config = {
    'symbols': ['SPY'],
    'rsi_period': 14
}
strategy = MomentumStrategy(config)
signals = strategy.generate_signals(data)

print(f"생성된 신호: {len(signals)}")
for signal in signals:
    print(signal)
```

## 성능 최적화

### 데이터베이스 최적화

```sql
-- TimescaleDB 최적화
-- 1. 하이퍼테이블 생성
SELECT create_hypertable('market_data', 'date', chunk_time_interval => INTERVAL '1 month');

-- 2. 인덱스 생성
CREATE INDEX idx_market_data_symbol_date ON market_data (symbol, date DESC);
CREATE INDEX idx_market_data_date ON market_data (date DESC);

-- 3. 압축 정책
ALTER TABLE market_data SET (
  timescaledb.compress,
  timescaledb.compress_segmentby = 'symbol'
);

SELECT add_compression_policy('market_data', INTERVAL '7 days');

-- 4. 집계 뷰
CREATE MATERIALIZED VIEW daily_stats AS
SELECT
  symbol,
  date_trunc('day', date) as day,
  first(open, date) as open,
  max(high) as high,
  min(low) as low,
  last(close, date) as close,
  sum(volume) as volume
FROM market_data
GROUP BY symbol, day
WITH NO DATA;

-- 5. 자동 새로고침
SELECT add_continuous_aggregate_policy('daily_stats',
  start_offset => INTERVAL '3 days',
  end_offset => INTERVAL '1 hour',
  schedule_interval => INTERVAL '1 hour'
);
```

### 캐싱 전략

```python
# cache/redis_cache.py
import redis
import pickle
from functools import wraps
from typing import Any

class RedisCache:
    def __init__(self, host='redis', port=6379, db=0):
        self.client = redis.StrictRedis(
            host=host,
            port=port,
            db=db,
            decode_responses=False
        )

    def cache_result(self, ttl=3600):
        """함수 결과 캐싱 데코레이터"""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                # 캐시 키 생성
                cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"

                # 캐시 확인
                cached = self.client.get(cache_key)
                if cached:
                    return pickle.loads(cached)

                # 함수 실행
                result = func(*args, **kwargs)

                # 결과 캐싱
                self.client.setex(
                    cache_key,
                    ttl,
                    pickle.dumps(result)
                )

                return result
            return wrapper
        return decorator

# 사용 예시
cache = RedisCache()

@cache.cache_result(ttl=300)  # 5분 캐싱
def get_latest_signals(strategy_name: str):
    # 비용이 큰 연산
    return calculate_signals(strategy_name)
```

### 비동기 처리

```python
# async_processing.py
import asyncio
from concurrent.futures import ThreadPoolExecutor
import aiohttp

class AsyncProcessor:
    def __init__(self, max_workers=10):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    async def fetch_multiple_symbols(self, symbols: list):
        """여러 심볼 동시 처리"""
        tasks = []
        async with aiohttp.ClientSession() as session:
            for symbol in symbols:
                task = self.fetch_symbol_data(session, symbol)
                tasks.append(task)

            results = await asyncio.gather(*tasks)
        return results

    async def fetch_symbol_data(self, session, symbol):
        """개별 심볼 데이터 조회"""
        url = f"https://api.example.com/data/{symbol}"
        async with session.get(url) as response:
            return await response.json()

    def run_in_executor(self, func, *args):
        """CPU 집약적 작업 비동기 실행"""
        loop = asyncio.get_event_loop()
        return loop.run_in_executor(self.executor, func, *args)
```