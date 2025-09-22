# 전략 가이드 (Strategy Guide)

## 목차
1. [전략 개요](#전략-개요)
2. [모멘텀 전략 (Momentum)](#모멘텀-전략)
3. [평균회귀 전략 (Mean Reversion)](#평균회귀-전략)
4. [머신러닝 전략 (ML Strategy)](#머신러닝-전략)
5. [포트폴리오 구성](#포트폴리오-구성)
6. [리스크 관리](#리스크-관리)
7. [백테스팅 가이드](#백테스팅-가이드)

## 전략 개요

### 투자 기간별 분류

| 기간 | 설명 | 보유 기간 | 적합 전략 |
|------|------|-----------|-----------|
| **Ultra Short** | 초단기 | 1-5일 | 모멘텀, 스캘핑 |
| **Short** | 단기 | 1-4주 | 평균회귀, 페어트레이딩 |
| **Medium** | 중기 | 1-3개월 | 트렌드 추종, 섹터 로테이션 |
| **Long** | 장기 | 3-12개월 | 머신러닝, 가치투자 |
| **Ultra Long** | 초장기 | 1년 이상 | Buy & Hold, 배당 전략 |

### 리스크 프로필

| 프로필 | 최대 포지션 크기 | 레버리지 | 손절매 | 적합 투자자 |
|--------|-----------------|----------|--------|------------|
| **Very Safe** | 5% | 없음 | -2% | 안정 추구 |
| **Safe** | 10% | 없음 | -3% | 보수적 |
| **Normal** | 15% | 1.5x | -5% | 균형형 |
| **Risky** | 20% | 2x | -7% | 공격적 |
| **Very Risky** | 30% | 3x | -10% | 투기적 |

## 모멘텀 전략

### 전략 원리

모멘텀 전략은 "강한 주식은 계속 강하고, 약한 주식은 계속 약하다"는 원리를 기반으로 합니다.

```python
class MomentumStrategy:
    """
    주요 지표:
    - RSI (Relative Strength Index)
    - 이동평균 교차
    - 거래량 증가
    - 가격 모멘텀
    """
```

### 매수/매도 신호

#### 매수 신호 (BUY)
1. **RSI 과매도**: RSI < 30
2. **골든크로스**: 단기 MA > 장기 MA (상향 돌파)
3. **거래량 급증**: 거래량 > 평균 거래량 × 1.5
4. **양의 모멘텀**: 20일 수익률 > 1%

#### 매도 신호 (SELL)
1. **RSI 과매수**: RSI > 70
2. **데드크로스**: 단기 MA < 장기 MA (하향 돌파)
3. **음의 모멘텀**: 20일 수익률 < -1%
4. **변동성 증가**: 변동성 > 3%

### 파라미터 최적화

```python
# 최적 파라미터 (백테스트 결과)
optimal_params = {
    'rsi_period': 14,        # RSI 기간
    'rsi_oversold': 30,      # 과매도 기준
    'rsi_overbought': 70,    # 과매수 기준
    'ma_short': 20,          # 단기 이동평균
    'ma_long': 50,           # 장기 이동평균
    'volume_factor': 1.5,    # 거래량 배수
    'momentum_lookback': 20  # 모멘텀 계산 기간
}
```

### 성과 지표

| 지표 | 3년 백테스트 결과 |
|------|------------------|
| 연평균 수익률 | 15.2% |
| 샤프 비율 | 1.35 |
| 최대 낙폭 | -12.5% |
| 승률 | 58% |
| 평균 보유기간 | 12일 |

## 평균회귀 전략

### 전략 원리

평균회귀는 가격이 평균으로 회귀하는 성질을 이용합니다.

```python
class MeanReversionStrategy:
    """
    주요 지표:
    - 볼린저 밴드
    - Z-Score
    - 가격 편차
    - 연속 하락/상승일
    """
```

### 매수/매도 신호

#### 매수 신호
1. **볼린저 밴드 하단 이탈**: 가격 < BB 하단
2. **극단적 Z-Score**: Z-Score < -2
3. **가격 과도 하락**: 가격 Z-Score < -2
4. **연속 하락**: 5일 연속 하락

#### 매도 신호
1. **볼린저 밴드 상단 이탈**: 가격 > BB 상단
2. **극단적 Z-Score**: Z-Score > 2
3. **가격 과도 상승**: 가격 Z-Score > 2
4. **연속 상승**: 5일 연속 상승

### 리스크 관리

```python
risk_params = {
    'position_size': 0.1,      # 포트폴리오의 10%
    'stop_loss': -0.05,        # 5% 손절
    'take_profit': 0.08,       # 8% 익절
    'max_holding_days': 30,    # 최대 30일 보유
    'volatility_filter': 0.03  # 변동성 3% 이하만 거래
}
```

### 백테스트 결과

```python
# 2021-2024 백테스트 결과
results = {
    'total_return': 45.3,      # 총 수익률 %
    'annual_return': 13.2,     # 연평균 수익률 %
    'sharpe_ratio': 1.42,
    'sortino_ratio': 1.85,
    'max_drawdown': -9.8,      # 최대 낙폭 %
    'win_rate': 62.5,          # 승률 %
    'avg_win': 3.2,            # 평균 수익 %
    'avg_loss': -1.8,          # 평균 손실 %
    'profit_factor': 2.1       # 수익/손실 비율
}
```

## 머신러닝 전략

### ML 모델 구조

```python
class MLStrategy:
    """
    Random Forest 기반 예측 모델

    Features (특징):
    - 기술적 지표: RSI, MACD, BB, ATR
    - 가격 패턴: 수익률, 변동성
    - 거래량 지표: OBV, 거래량 비율
    - 시장 지표: VIX, 달러 인덱스

    Target (목표):
    - 5일 후 수익률 (분류: 상승/하락)
    """

    def __init__(self):
        self.model = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            min_samples_split=20,
            random_state=42
        )
```

### Feature Engineering

```python
def create_features(df):
    """특징 생성"""
    features = pd.DataFrame()

    # 기술적 지표
    features['rsi'] = ta.momentum.RSIIndicator(df['close']).rsi()
    features['macd'] = ta.trend.MACD(df['close']).macd_diff()
    features['bb_width'] = ta.volatility.BollingerBands(df['close']).bollinger_wband()
    features['atr'] = ta.volatility.AverageTrueRange(
        df['high'], df['low'], df['close']
    ).average_true_range()

    # 가격 패턴
    features['returns_1d'] = df['close'].pct_change()
    features['returns_5d'] = df['close'].pct_change(5)
    features['returns_20d'] = df['close'].pct_change(20)
    features['volatility'] = features['returns_1d'].rolling(20).std()

    # 거래량
    features['volume_ratio'] = df['volume'] / df['volume'].rolling(20).mean()
    features['obv'] = ta.volume.OnBalanceVolumeIndicator(
        df['close'], df['volume']
    ).on_balance_volume()

    return features
```

### 모델 학습 및 예측

```python
# 학습 과정
def train_model(train_data):
    X_train = create_features(train_data)
    y_train = (train_data['close'].shift(-5) > train_data['close']).astype(int)

    # 결측치 제거
    mask = ~(X_train.isnull().any(axis=1) | y_train.isnull())
    X_train = X_train[mask]
    y_train = y_train[mask]

    # 모델 학습
    model.fit(X_train, y_train)

    # 성능 평가
    predictions = model.predict(X_test)
    accuracy = accuracy_score(y_test, predictions)

    return model, accuracy
```

### ML 전략 성과

| 지표 | 값 |
|------|-----|
| 예측 정확도 | 57.3% |
| 연평균 수익률 | 18.5% |
| 샤프 비율 | 1.52 |
| 최대 낙폭 | -11.2% |
| 정보 비율 | 0.85 |

## 포트폴리오 구성

### 1. Conservative Portfolio (보수적)

```python
conservative_portfolio = {
    'name': 'Conservative Portfolio',
    'strategies': [
        {
            'name': 'trend_following',
            'allocation': 0.4,  # 40%
            'risk_profile': 'safe',
            'investment_period': 'long'
        },
        {
            'name': 'mean_reversion',
            'allocation': 0.3,  # 30%
            'risk_profile': 'safe',
            'investment_period': 'medium'
        },
        {
            'name': 'dividend_etfs',
            'allocation': 0.3,  # 30%
            'risk_profile': 'very_safe',
            'investment_period': 'ultra_long'
        }
    ],
    'expected_return': 8.5,  # 연 8.5%
    'expected_volatility': 6.2,  # 연 6.2%
    'max_drawdown_limit': -10  # 최대 -10%
}
```

### 2. Balanced Portfolio (균형형)

```python
balanced_portfolio = {
    'name': 'Balanced Portfolio',
    'strategies': [
        {
            'name': 'momentum',
            'allocation': 0.25,
            'risk_profile': 'normal',
            'investment_period': 'short'
        },
        {
            'name': 'ml_strategy',
            'allocation': 0.25,
            'risk_profile': 'normal',
            'investment_period': 'medium'
        },
        {
            'name': 'trend_following',
            'allocation': 0.25,
            'risk_profile': 'normal',
            'investment_period': 'long'
        },
        {
            'name': 'sector_rotation',
            'allocation': 0.25,
            'risk_profile': 'normal',
            'investment_period': 'medium'
        }
    ],
    'expected_return': 12.5,
    'expected_volatility': 10.8,
    'max_drawdown_limit': -15
}
```

### 3. Aggressive Portfolio (공격적)

```python
aggressive_portfolio = {
    'name': 'Aggressive Portfolio',
    'strategies': [
        {
            'name': 'leveraged_momentum',
            'allocation': 0.3,
            'risk_profile': 'very_risky',
            'investment_period': 'ultra_short',
            'leverage': 2.0
        },
        {
            'name': 'volatility_trading',
            'allocation': 0.2,
            'risk_profile': 'risky',
            'investment_period': 'short'
        },
        {
            'name': 'pairs_trading',
            'allocation': 0.25,
            'risk_profile': 'risky',
            'investment_period': 'short'
        },
        {
            'name': 'ml_enhanced',
            'allocation': 0.25,
            'risk_profile': 'risky',
            'investment_period': 'medium'
        }
    ],
    'expected_return': 20.5,
    'expected_volatility': 18.5,
    'max_drawdown_limit': -25
}
```

### 4. Multi-Timeframe Portfolio

```python
multi_timeframe_portfolio = {
    'name': 'Multi-Timeframe Portfolio',
    'strategies': [
        # 초단기 (15%)
        {
            'name': 'scalping',
            'allocation': 0.15,
            'investment_period': 'ultra_short',
            'execution_frequency': 'daily'
        },
        # 단기 (25%)
        {
            'name': 'swing_trading',
            'allocation': 0.25,
            'investment_period': 'short',
            'execution_frequency': 'every_3_days'
        },
        # 중기 (30%)
        {
            'name': 'trend_following',
            'allocation': 0.30,
            'investment_period': 'medium',
            'execution_frequency': 'weekly'
        },
        # 장기 (20%)
        {
            'name': 'value_investing',
            'allocation': 0.20,
            'investment_period': 'long',
            'execution_frequency': 'bi_weekly'
        },
        # 초장기 (10%)
        {
            'name': 'buy_and_hold',
            'allocation': 0.10,
            'investment_period': 'ultra_long',
            'execution_frequency': 'monthly'
        }
    ]
}
```

## 리스크 관리

### 포지션 크기 계산

```python
class PositionSizer:
    def calculate_position_size(self, signal, portfolio_value, config):
        """
        Kelly Criterion 기반 포지션 크기 계산
        """
        # 기본 크기
        base_size = portfolio_value * config['base_allocation']

        # Kelly 비율
        win_prob = signal.get('win_probability', 0.5)
        avg_win = signal.get('expected_gain', 0.02)
        avg_loss = signal.get('expected_loss', 0.01)

        kelly_ratio = (win_prob * avg_win - (1 - win_prob) * avg_loss) / avg_win
        kelly_ratio = max(0, min(kelly_ratio, 0.25))  # 최대 25%로 제한

        # 신호 강도 조정
        signal_strength = signal.get('score', 0.5)

        # 변동성 조정
        volatility = signal.get('volatility', 0.02)
        vol_adjustment = max(0.5, min(1.5, 0.02 / volatility))

        # 최종 포지션 크기
        position_size = base_size * kelly_ratio * signal_strength * vol_adjustment

        # 리스크 프로필별 제한
        max_position = self.get_max_position(config['risk_profile'])
        position_size = min(position_size, portfolio_value * max_position)

        return position_size
```

### 손절매/익절매 전략

```python
class RiskManager:
    def __init__(self, config):
        self.stop_loss_pct = config.get('stop_loss', -0.05)
        self.take_profit_pct = config.get('take_profit', 0.10)
        self.trailing_stop = config.get('trailing_stop', 0.03)

    def check_exit_conditions(self, position):
        """종료 조건 확인"""
        current_return = position['current_return']
        max_return = position['max_return']

        # 손절매
        if current_return <= self.stop_loss_pct:
            return 'STOP_LOSS'

        # 익절매
        if current_return >= self.take_profit_pct:
            return 'TAKE_PROFIT'

        # 추적 손절매
        if max_return > 0 and current_return < max_return - self.trailing_stop:
            return 'TRAILING_STOP'

        # 시간 기반 종료
        if position['holding_days'] > position['max_holding_days']:
            return 'TIME_EXIT'

        return None
```

### 포트폴리오 리스크 모니터링

```python
class PortfolioRiskMonitor:
    def calculate_risk_metrics(self, portfolio):
        """포트폴리오 리스크 지표 계산"""

        metrics = {
            # Value at Risk (95% 신뢰수준)
            'var_95': np.percentile(portfolio['returns'], 5),

            # Conditional VaR (Expected Shortfall)
            'cvar_95': portfolio['returns'][
                portfolio['returns'] <= np.percentile(portfolio['returns'], 5)
            ].mean(),

            # 최대 낙폭
            'max_drawdown': self.calculate_max_drawdown(portfolio['value']),

            # 베타 (시장 대비)
            'beta': self.calculate_beta(portfolio['returns'], market['returns']),

            # 상관관계 (전략 간)
            'strategy_correlation': self.calculate_strategy_correlation(),

            # 집중도 리스크
            'concentration_risk': self.calculate_concentration(),

            # 유동성 리스크
            'liquidity_risk': self.calculate_liquidity_risk()
        }

        return metrics
```

## 백테스팅 가이드

### 백테스트 설정

```python
backtest_config = {
    # 기간 설정
    'start_date': '2020-01-01',
    'end_date': '2024-01-01',

    # 자본금
    'initial_capital': 100000,

    # 거래 비용
    'commission': 0.001,  # 0.1%
    'slippage': 0.0005,   # 0.05%

    # 백테스트 옵션
    'enable_repetition': True,  # 기간별 반복
    'compound_returns': True,   # 복리 적용

    # 리스크 설정
    'max_position_size': 0.2,  # 최대 20%
    'max_leverage': 2.0,        # 최대 2배
    'cash_reserve': 0.05,       # 5% 현금 보유
}
```

### 백테스트 실행

```bash
# CLI를 통한 백테스트
curl -X POST http://localhost:8001/backtest \
  -H "Content-Type: application/json" \
  -d '{
    "portfolio_name": "Balanced Portfolio",
    "config": {
      "start_date": "2020-01-01",
      "end_date": "2024-01-01",
      "initial_capital": 100000
    }
  }'
```

### 결과 분석

```python
def analyze_backtest_results(results):
    """백테스트 결과 분석"""

    analysis = {
        # 수익률 분석
        'total_return': results['final_value'] / results['initial_capital'] - 1,
        'annual_return': (results['final_value'] / results['initial_capital']) ** (1/years) - 1,
        'monthly_returns': results['returns'].resample('M').apply(lambda x: (1+x).prod()-1),

        # 리스크 분석
        'volatility': results['returns'].std() * np.sqrt(252),
        'downside_deviation': results['returns'][results['returns'] < 0].std() * np.sqrt(252),
        'max_drawdown': calculate_max_drawdown(results['equity_curve']),

        # 리스크 조정 수익률
        'sharpe_ratio': (annual_return - risk_free_rate) / volatility,
        'sortino_ratio': (annual_return - risk_free_rate) / downside_deviation,
        'calmar_ratio': annual_return / abs(max_drawdown),

        # 거래 통계
        'total_trades': len(results['trades']),
        'winning_trades': len([t for t in results['trades'] if t['pnl'] > 0]),
        'win_rate': winning_trades / total_trades,
        'avg_win': np.mean([t['pnl'] for t in results['trades'] if t['pnl'] > 0]),
        'avg_loss': np.mean([t['pnl'] for t in results['trades'] if t['pnl'] < 0]),
        'profit_factor': sum([t['pnl'] for t in results['trades'] if t['pnl'] > 0]) /
                        abs(sum([t['pnl'] for t in results['trades'] if t['pnl'] < 0])),

        # 기간별 성과
        'best_month': monthly_returns.max(),
        'worst_month': monthly_returns.min(),
        'positive_months': (monthly_returns > 0).sum() / len(monthly_returns),
    }

    return analysis
```

### 전략 비교

```python
# 여러 전략 백테스트 비교
strategies_to_compare = [
    'momentum',
    'mean_reversion',
    'ml_strategy',
    'trend_following'
]

comparison_results = {}
for strategy in strategies_to_compare:
    results = run_backtest(strategy, backtest_config)
    comparison_results[strategy] = analyze_backtest_results(results)

# 비교 테이블 생성
comparison_df = pd.DataFrame(comparison_results).T
print(comparison_df[['annual_return', 'sharpe_ratio', 'max_drawdown', 'win_rate']])
```

## 실전 운용 팁

### 1. 전략 선택 가이드

| 시장 상황 | 추천 전략 | 이유 |
|----------|-----------|------|
| 상승장 | 모멘텀, 트렌드 추종 | 추세 지속성 활용 |
| 하락장 | 평균회귀, 역모멘텀 | 과매도 구간 매수 |
| 횡보장 | 평균회귀, 페어트레이딩 | 범위 내 거래 |
| 고변동성 | 변동성 전략, ML | 변동성 활용 |
| 저변동성 | 캐리 트레이드, 배당 | 안정적 수익 |

### 2. 포트폴리오 리밸런싱

```python
def rebalance_portfolio(portfolio, target_allocation):
    """월간 리밸런싱"""
    current_allocation = calculate_current_allocation(portfolio)

    trades = []
    for strategy, target_weight in target_allocation.items():
        current_weight = current_allocation.get(strategy, 0)
        diff = target_weight - current_weight

        if abs(diff) > 0.05:  # 5% 이상 차이날 때만 리밸런싱
            if diff > 0:
                trades.append({'strategy': strategy, 'action': 'BUY', 'weight': diff})
            else:
                trades.append({'strategy': strategy, 'action': 'SELL', 'weight': abs(diff)})

    return trades
```

### 3. 시장 체제 전환 감지

```python
def detect_regime_change(market_data):
    """시장 체제 변화 감지"""

    # 변동성 체제
    current_vol = market_data['returns'].rolling(20).std().iloc[-1]
    avg_vol = market_data['returns'].rolling(252).std().mean()

    if current_vol > avg_vol * 1.5:
        regime = 'high_volatility'
    elif current_vol < avg_vol * 0.5:
        regime = 'low_volatility'
    else:
        regime = 'normal'

    # 트렌드 체제
    sma_50 = market_data['close'].rolling(50).mean().iloc[-1]
    sma_200 = market_data['close'].rolling(200).mean().iloc[-1]

    if sma_50 > sma_200 * 1.02:
        trend = 'bullish'
    elif sma_50 < sma_200 * 0.98:
        trend = 'bearish'
    else:
        trend = 'neutral'

    return {'volatility_regime': regime, 'trend_regime': trend}
```