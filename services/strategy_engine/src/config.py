import os
from dotenv import load_dotenv
from typing import List, Dict, Any

load_dotenv()


class Config:
    """Strategy Engine Configuration"""

    # Database URLs
    DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://quant_user:quant_pass@localhost:5432/quant_trading')
    TIMESCALE_URL = os.getenv('TIMESCALE_URL', 'postgresql://timescale_user:timescale_pass@localhost:5433/market_data')
    REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')
    RABBITMQ_URL = os.getenv('RABBITMQ_URL', 'amqp://admin:admin@localhost:5672/')

    # ============================================================================
    # MULTIPLE STRATEGY PORTFOLIOS CONFIGURATION
    # ============================================================================

    # Default Portfolio Configurations
    # 여러 전략을 동시에 운영하는 포트폴리오 설정
    DEFAULT_PORTFOLIOS = [
        {
            'name': 'Conservative Portfolio',
            'description': '보수적 포트폴리오 - 안전 위주의 장기 투자',
            'total_allocation': 1.0,
            'strategies': [
                {
                    'name': 'long_term_trend',
                    'type': 'trend_following',
                    'risk_profile': 'safe',
                    'investment_period': 'long',
                    'allocation': 0.4,  # 40%
                    'parameters': {
                        'ma_period': 200,
                        'position_size': 0.1
                    }
                },
                {
                    'name': 'mean_reversion_safe',
                    'type': 'mean_reversion',
                    'risk_profile': 'very_safe',
                    'investment_period': 'medium',
                    'allocation': 0.3,  # 30%
                    'parameters': {
                        'bb_period': 20,
                        'z_score_threshold': 3
                    }
                },
                {
                    'name': 'dividend_etf',
                    'type': 'buy_and_hold',
                    'risk_profile': 'very_safe',
                    'investment_period': 'ultra_long',
                    'allocation': 0.3,  # 30%
                    'parameters': {
                        'etfs': ['VIG', 'DVY', 'SCHD']
                    }
                }
            ]
        },
        {
            'name': 'Balanced Portfolio',
            'description': '균형 포트폴리오 - 중간 위험/수익',
            'total_allocation': 1.0,
            'strategies': [
                {
                    'name': 'momentum_medium',
                    'type': 'momentum',
                    'risk_profile': 'normal',
                    'investment_period': 'medium',
                    'allocation': 0.25,  # 25%
                    'parameters': {
                        'rsi_period': 14,
                        'ma_short': 20,
                        'ma_long': 50
                    }
                },
                {
                    'name': 'ml_strategy',
                    'type': 'machine_learning',
                    'risk_profile': 'normal',
                    'investment_period': 'short',
                    'allocation': 0.25,  # 25%
                    'parameters': {
                        'model_type': 'ensemble',
                        'retrain_days': 30
                    }
                },
                {
                    'name': 'trend_following_medium',
                    'type': 'trend_following',
                    'risk_profile': 'normal',
                    'investment_period': 'medium',
                    'allocation': 0.25,  # 25%
                    'parameters': {
                        'ma_period': 50
                    }
                },
                {
                    'name': 'sector_rotation',
                    'type': 'sector_rotation',
                    'risk_profile': 'normal',
                    'investment_period': 'medium',
                    'allocation': 0.25,  # 25%
                    'parameters': {
                        'sectors': ['XLK', 'XLF', 'XLE', 'XLV']
                    }
                }
            ]
        },
        {
            'name': 'Aggressive Portfolio',
            'description': '공격적 포트폴리오 - 고위험/고수익',
            'total_allocation': 1.0,
            'strategies': [
                {
                    'name': 'leveraged_momentum',
                    'type': 'momentum',
                    'risk_profile': 'very_risky',
                    'investment_period': 'ultra_short',
                    'allocation': 0.3,  # 30%
                    'parameters': {
                        'etfs': ['TQQQ', 'SOXL', 'UPRO'],
                        'rsi_period': 7,
                        'stop_loss': 0.05
                    }
                },
                {
                    'name': 'volatility_trading',
                    'type': 'volatility',
                    'risk_profile': 'risky',
                    'investment_period': 'short',
                    'allocation': 0.2,  # 20%
                    'parameters': {
                        'vix_threshold': 20,
                        'etfs': ['UVXY', 'SVXY']
                    }
                },
                {
                    'name': 'pairs_trading_aggressive',
                    'type': 'pairs_trading',
                    'risk_profile': 'risky',
                    'investment_period': 'short',
                    'allocation': 0.25,  # 25%
                    'parameters': {
                        'pairs': [['QQQ', 'SPY'], ['GLD', 'SLV']]
                    }
                },
                {
                    'name': 'ml_aggressive',
                    'type': 'machine_learning',
                    'risk_profile': 'risky',
                    'investment_period': 'ultra_short',
                    'allocation': 0.25,  # 25%
                    'parameters': {
                        'model_type': 'deep_learning',
                        'min_confidence': 0.7
                    }
                }
            ]
        },
        {
            'name': 'Multi-Timeframe Portfolio',
            'description': '다중 시간대 포트폴리오 - 다양한 기간 혼합',
            'total_allocation': 1.0,
            'strategies': [
                {
                    'name': 'ultra_short_scalping',
                    'type': 'scalping',
                    'risk_profile': 'risky',
                    'investment_period': 'ultra_short',
                    'allocation': 0.15,  # 15% - 1-5일 주기
                    'parameters': {
                        'profit_target': 0.01,
                        'stop_loss': 0.005
                    }
                },
                {
                    'name': 'short_term_momentum',
                    'type': 'momentum',
                    'risk_profile': 'normal',
                    'investment_period': 'short',
                    'allocation': 0.2,  # 20% - 1-4주 주기
                    'parameters': {
                        'rsi_period': 9
                    }
                },
                {
                    'name': 'medium_term_trend',
                    'type': 'trend_following',
                    'risk_profile': 'normal',
                    'investment_period': 'medium',
                    'allocation': 0.25,  # 25% - 1-3개월 주기
                    'parameters': {
                        'ma_period': 50
                    }
                },
                {
                    'name': 'long_term_value',
                    'type': 'value_investing',
                    'risk_profile': 'safe',
                    'investment_period': 'long',
                    'allocation': 0.25,  # 25% - 3-12개월 주기
                    'parameters': {
                        'pe_threshold': 15
                    }
                },
                {
                    'name': 'ultra_long_hold',
                    'type': 'buy_and_hold',
                    'risk_profile': 'very_safe',
                    'investment_period': 'ultra_long',
                    'allocation': 0.15,  # 15% - 1년+ 보유
                    'parameters': {
                        'etfs': ['VOO', 'VTI']
                    }
                }
            ]
        }
    ]

    # Active Portfolios Configuration
    # 동시에 운영할 포트폴리오 목록 (여러 개 동시 운영 가능)
    ACTIVE_PORTFOLIOS = os.getenv('ACTIVE_PORTFOLIOS', 'Balanced Portfolio,Multi-Timeframe Portfolio').split(',')

    # ============================================================================
    # STRATEGY PERIOD CONFIGURATION
    # ============================================================================

    # Investment Period Definitions (in days)
    # 각 투자 기간의 실제 일수 정의
    PERIOD_DAYS = {
        'ultra_short': {'min': 1, 'max': 5, 'rebalance': 1},      # 초단기: 1-5일
        'short': {'min': 7, 'max': 28, 'rebalance': 7},          # 단기: 1-4주
        'medium': {'min': 30, 'max': 90, 'rebalance': 14},       # 중기: 1-3개월
        'long': {'min': 90, 'max': 365, 'rebalance': 30},        # 장기: 3-12개월
        'ultra_long': {'min': 365, 'max': None, 'rebalance': 90} # 초장기: 1년+
    }

    # Strategy Execution Frequency
    # 전략별 실행 주기 설정
    EXECUTION_FREQUENCY = {
        'ultra_short': 1,    # 매일 실행
        'short': 3,          # 3일마다 실행
        'medium': 7,         # 주 1회 실행
        'long': 14,          # 2주마다 실행
        'ultra_long': 30     # 월 1회 실행
    }

    # ============================================================================
    # BACKTESTING CONFIGURATION
    # ============================================================================

    # Multi-Period Backtesting Settings
    # 백테스트 시 단기 전략 반복 설정
    BACKTEST_CONFIG = {
        'enable_period_repetition': True,  # 기간별 자동 반복 활성화
        'compound_returns': True,          # 복리 수익 계산
        'reinvest_profits': True,          # 수익 재투자
        'rebalance_portfolio': True,       # 주기적 리밸런싱
        'rebalance_frequency': 30,         # 리밸런싱 주기 (일)
        'min_trade_amount': 100,           # 최소 거래 금액
        'max_position_per_strategy': 0.3,  # 전략당 최대 포지션
        'emergency_stop_loss': 0.2         # 긴급 손절 라인 (20%)
    }

    # ============================================================================
    # RISK MANAGEMENT
    # ============================================================================

    # Risk Profiles with Multiple Parameters
    RISK_PROFILES = {
        'very_safe': {
            'max_position': 0.05,
            'stop_loss': 0.02,
            'leverage': 1.0,
            'max_strategies': 3,
            'allowed_etfs': ['VOO', 'VTI', 'BND', 'AGG']
        },
        'safe': {
            'max_position': 0.1,
            'stop_loss': 0.03,
            'leverage': 1.0,
            'max_strategies': 5,
            'allowed_etfs': ['SPY', 'QQQ', 'IWM', 'EFA', 'TLT']
        },
        'normal': {
            'max_position': 0.15,
            'stop_loss': 0.05,
            'leverage': 1.5,
            'max_strategies': 7,
            'allowed_etfs': None  # All ETFs allowed
        },
        'risky': {
            'max_position': 0.2,
            'stop_loss': 0.07,
            'leverage': 2.0,
            'max_strategies': 10,
            'allowed_etfs': None
        },
        'very_risky': {
            'max_position': 0.3,
            'stop_loss': 0.1,
            'leverage': 3.0,
            'max_strategies': 15,
            'allowed_etfs': None,
            'allow_leveraged_etfs': True
        }
    }

    # ============================================================================
    # PORTFOLIO ALLOCATION RULES
    # ============================================================================

    # Allocation Constraints
    ALLOCATION_RULES = {
        'min_allocation_per_strategy': 0.05,     # 최소 5% 할당
        'max_allocation_per_strategy': 0.4,      # 최대 40% 할당
        'max_correlation_between_strategies': 0.7, # 전략 간 최대 상관계수
        'min_strategies_in_portfolio': 3,        # 최소 전략 수
        'max_strategies_in_portfolio': 10,       # 최대 전략 수
        'cash_reserve': 0.05                     # 현금 보유 비율 5%
    }

    # ============================================================================
    # PERFORMANCE TRACKING
    # ============================================================================

    # Performance Metrics to Track
    TRACK_METRICS = [
        'total_return',
        'annualized_return',
        'sharpe_ratio',
        'sortino_ratio',
        'max_drawdown',
        'win_rate',
        'profit_factor',
        'calmar_ratio',
        'recovery_time',
        'var_95',  # Value at Risk
        'cvar_95'  # Conditional VaR
    ]

    # Performance Thresholds for Alerts
    ALERT_THRESHOLDS = {
        'max_drawdown': -0.15,      # Alert if drawdown > 15%
        'daily_loss': -0.05,         # Alert if daily loss > 5%
        'strategy_underperformance': -0.1,  # Alert if strategy underperforms by 10%
        'correlation_spike': 0.9     # Alert if correlation > 0.9
    }