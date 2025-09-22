# 개발 가이드 (Development Guide)

## 목차
1. [프로젝트 구조](#프로젝트-구조)
2. [개발 환경 설정](#개발-환경-설정)
3. [서비스별 개발 가이드](#서비스별-개발-가이드)
4. [코드 컨벤션](#코드-컨벤션)
5. [테스트 가이드](#테스트-가이드)
6. [디버깅](#디버깅)

## 프로젝트 구조

```
quant_trading/
├── services/                   # 마이크로서비스
│   ├── data_collector/        # 시장 데이터 수집 서비스
│   ├── strategy_engine/       # 전략 실행 엔진
│   ├── backtesting/          # 백테스팅 서비스
│   ├── order_generator/      # 주문 생성 서비스
│   ├── api_gateway/          # API 게이트웨이
│   └── admin_ui/             # 관리자 대시보드
├── shared/                    # 공통 라이브러리
├── infrastructure/           # 인프라 설정
├── docs/                     # 문서
└── docker-compose.yml        # Docker 구성
```

## 개발 환경 설정

### 1. 필수 도구 설치

```bash
# Python 3.11 설치
sudo apt update
sudo apt install python3.11 python3.11-venv python3-pip

# Node.js 18+ 설치
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# Docker & Docker Compose 설치
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Docker Compose 설치
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### 2. 프로젝트 클론 및 설정

```bash
# 프로젝트 클론
git clone <repository-url>
cd quant_trading

# 환경 변수 설정
cp .env.example .env

# .env 파일 편집 (필수 항목 설정)
nano .env
```

### 3. 로컬 개발 환경 실행

```bash
# 전체 서비스 빌드
make build

# 데이터베이스만 먼저 실행
docker-compose up -d postgres timescaledb redis rabbitmq

# 데이터베이스 초기화
make db-init

# 개별 서비스 개발 모드 실행
cd services/data_collector
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
python src/main.py
```

## 서비스별 개발 가이드

### Data Collector Service

```python
# services/data_collector/src/collectors.py

from abc import ABC, abstractmethod
import pandas as pd

class BaseCollector(ABC):
    """데이터 수집기 베이스 클래스"""

    def __init__(self, priority=1):
        self.priority = priority

    @abstractmethod
    async def fetch_data(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """데이터 수집 메서드 - 반드시 구현"""
        pass

    @abstractmethod
    def validate_data(self, df: pd.DataFrame) -> bool:
        """데이터 검증 메서드"""
        pass

# 새로운 데이터 소스 추가 예시
class MyCustomCollector(BaseCollector):
    def __init__(self):
        super().__init__(priority=3)
        # 초기화 코드

    async def fetch_data(self, symbol, start_date, end_date):
        # 데이터 수집 로직
        return df

    def validate_data(self, df):
        # 데이터 검증 로직
        return True
```

### Strategy Engine

```python
# services/strategy_engine/src/strategies/custom_strategy.py

from . import BaseStrategy
import pandas as pd
from typing import List, Dict

class CustomStrategy(BaseStrategy):
    """커스텀 전략 구현 예시"""

    def __init__(self, config: Dict):
        super().__init__(config)
        # 전략 파라미터 설정
        self.param1 = config.get('param1', 10)
        self.param2 = config.get('param2', 20)

    async def generate_signals(self, market_data: pd.DataFrame) -> List[Dict]:
        """
        거래 신호 생성

        Args:
            market_data: OHLCV 데이터

        Returns:
            List[Dict]: 거래 신호 리스트
        """
        signals = []

        # 전략 로직 구현
        for symbol in market_data['symbol'].unique():
            df = market_data[market_data['symbol'] == symbol]

            # 지표 계산
            # ...

            # 신호 생성
            if condition_met:
                signal = self.create_signal(
                    symbol=symbol,
                    action='BUY',  # or 'SELL'
                    score=0.8,
                    metadata={'reason': 'condition_met'}
                )
                signals.append(signal)

        return signals

    def calculate_position_size(self, signal: Dict, portfolio_value: float) -> float:
        """포지션 크기 계산"""
        base_size = super().calculate_position_size(signal, portfolio_value)
        # 커스텀 로직 추가 가능
        return base_size
```

### 백테스팅 서비스

```python
# services/backtesting/src/backtester.py

class Backtester:
    """백테스팅 엔진"""

    def run_backtest(self,
                     strategy_name: str,
                     start_date: str,
                     end_date: str,
                     initial_capital: float = 100000) -> Dict:
        """
        백테스트 실행

        Returns:
            Dict: 백테스트 결과
                - returns: 수익률 시계열
                - metrics: 성과 지표
                - trades: 거래 내역
        """
        # 데이터 로드
        data = self.load_data(start_date, end_date)

        # 전략 실행
        signals = self.strategy.generate_signals(data)

        # 포트폴리오 시뮬레이션
        portfolio = self.simulate_portfolio(signals, initial_capital)

        # 성과 계산
        metrics = self.calculate_metrics(portfolio)

        return {
            'returns': portfolio['returns'],
            'metrics': metrics,
            'trades': portfolio['trades']
        }
```

## 코드 컨벤션

### Python 코드 스타일

```python
# PEP 8 준수
# Black formatter 사용

# 클래스명: CamelCase
class MyStrategy:
    pass

# 함수명: snake_case
def calculate_returns():
    pass

# 상수: UPPER_SNAKE_CASE
MAX_RETRY_COUNT = 3

# Type hints 사용
from typing import List, Dict, Optional

def process_data(data: pd.DataFrame) -> Optional[Dict[str, float]]:
    """
    함수 설명

    Args:
        data: 입력 데이터

    Returns:
        처리된 결과 또는 None
    """
    pass
```

### JavaScript/TypeScript 코드 스타일

```typescript
// TypeScript 사용 권장
// ESLint + Prettier 사용

// 인터페이스 정의
interface TradingSignal {
  symbol: string;
  action: 'BUY' | 'SELL';
  quantity: number;
  timestamp: Date;
}

// 함수 정의
const calculatePosition = (
  signal: TradingSignal,
  portfolio: Portfolio
): number => {
  // 구현
  return position;
};

// React 컴포넌트
const TradingDashboard: React.FC<Props> = ({ data }) => {
  const [signals, setSignals] = useState<TradingSignal[]>([]);

  useEffect(() => {
    // Side effects
  }, [data]);

  return (
    <div>
      {/* JSX */}
    </div>
  );
};
```

## 테스트 가이드

### 단위 테스트 작성

```python
# tests/test_strategy.py

import pytest
import pandas as pd
from services.strategy_engine.src.strategies.momentum import MomentumStrategy

class TestMomentumStrategy:
    @pytest.fixture
    def strategy(self):
        config = {
            'rsi_period': 14,
            'ma_short': 20,
            'ma_long': 50
        }
        return MomentumStrategy(config)

    @pytest.fixture
    def sample_data(self):
        # 테스트용 데이터 생성
        return pd.DataFrame({
            'symbol': ['SPY'] * 100,
            'date': pd.date_range('2023-01-01', periods=100),
            'close': np.random.randn(100).cumsum() + 100,
            'volume': np.random.randint(1000000, 10000000, 100)
        })

    async def test_generate_signals(self, strategy, sample_data):
        signals = await strategy.generate_signals(sample_data)

        assert isinstance(signals, list)
        assert all('symbol' in s for s in signals)
        assert all('action' in s for s in signals)
        assert all(s['action'] in ['BUY', 'SELL'] for s in signals)
```

### 통합 테스트

```bash
# 통합 테스트 실행
docker-compose -f docker-compose.test.yml up --abort-on-container-exit

# 특정 서비스 테스트
docker-compose exec strategy_engine pytest tests/

# 커버리지 확인
docker-compose exec strategy_engine pytest --cov=src tests/
```

## 디버깅

### 로그 확인

```bash
# 전체 로그 확인
docker-compose logs -f

# 특정 서비스 로그
docker-compose logs -f strategy_engine

# 로그 파일 위치
tail -f /var/log/quant_trading/strategy_engine.log
```

### 디버거 설정

```python
# Python 디버거 (pdb) 사용
import pdb

def debug_function():
    data = fetch_data()
    pdb.set_trace()  # 브레이크포인트
    result = process_data(data)
    return result

# VS Code 디버거 설정 (.vscode/launch.json)
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Python: Strategy Engine",
            "type": "python",
            "request": "launch",
            "program": "${workspaceFolder}/services/strategy_engine/src/main.py",
            "console": "integratedTerminal",
            "env": {
                "PYTHONPATH": "${workspaceFolder}/services/strategy_engine"
            }
        }
    ]
}
```

### 성능 프로파일링

```python
# cProfile 사용
import cProfile
import pstats

def profile_strategy():
    profiler = cProfile.Profile()
    profiler.enable()

    # 프로파일링할 코드
    strategy.generate_signals(data)

    profiler.disable()
    stats = pstats.Stats(profiler)
    stats.sort_stats('cumulative')
    stats.print_stats(20)  # 상위 20개 함수
```

## 데이터베이스 작업

### 마이그레이션

```sql
-- migrations/001_create_tables.sql
CREATE TABLE IF NOT EXISTS portfolios (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id UUID REFERENCES portfolios(id),
    symbol VARCHAR(20) NOT NULL,
    action VARCHAR(10) NOT NULL,
    quantity INTEGER NOT NULL,
    price DECIMAL(10, 2),
    executed_at TIMESTAMP
);
```

### 데이터베이스 접속

```bash
# PostgreSQL 접속
docker-compose exec postgres psql -U postgres -d quant_trading

# TimescaleDB 접속
docker-compose exec timescaledb psql -U timescale_user -d market_data

# Redis CLI
docker-compose exec redis redis-cli
```

## 배포 준비

### 빌드 최적화

```dockerfile
# Dockerfile 멀티스테이지 빌드
FROM python:3.11-slim as builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --user -r requirements.txt

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY . .
ENV PATH=/root/.local/bin:$PATH
CMD ["python", "src/main.py"]
```

### 환경별 설정

```python
# config.py
import os

class Config:
    """기본 설정"""
    DEBUG = False
    TESTING = False
    DATABASE_URI = os.getenv('DATABASE_URI')

class DevelopmentConfig(Config):
    """개발 환경 설정"""
    DEBUG = True

class ProductionConfig(Config):
    """프로덕션 환경 설정"""
    DEBUG = False

# 환경별 설정 선택
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}

current_config = config[os.getenv('ENVIRONMENT', 'default')]()
```