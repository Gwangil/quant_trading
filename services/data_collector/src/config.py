import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://timescale_user:timescale_pass@localhost:5433/market_data')
    REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')
    RABBITMQ_URL = os.getenv('RABBITMQ_URL', 'amqp://admin:admin@localhost:5672/')

    ALPHA_VANTAGE_API_KEY = os.getenv('ALPHA_VANTAGE_API_KEY', '')

    DEFAULT_ETFS = [
        'SPY', 'QQQ', 'DIA', 'IWM', 'VTI', 'VOO', 'EFA', 'EEM', 'GLD', 'SLV',
        'TLT', 'IEF', 'LQD', 'HYG', 'AGG', 'BND', 'VNQ', 'XLF', 'XLK', 'XLE',
        'TQQQ', 'SQQQ', 'UPRO', 'SPXU', 'TMF', 'TMV', 'UVXY', 'SVXY', 'SOXL', 'SOXS',
        'TNA', 'TZA', 'FAS', 'FAZ', 'LABU', 'LABD', 'JNUG', 'JDST', 'GUSH', 'DRIP'
    ]

    REALTIME_ETFS = [
        'SPY', 'QQQ', 'TQQQ', 'SQQQ', 'UVXY', 'VIX'
    ]

    MAX_RETRIES = 3
    RETRY_DELAY = 5
    CACHE_TTL = 3600