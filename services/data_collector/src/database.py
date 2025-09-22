import pandas as pd
from sqlalchemy import create_engine, text, MetaData, Table, Column, Integer, String, Float, DateTime, BigInteger, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
Base = declarative_base()


class DatabaseManager:
    def __init__(self, config):
        self.engine = create_engine(config.DATABASE_URL)
        self.Session = sessionmaker(bind=self.engine)
        self.metadata = MetaData()

    def initialize(self):
        """Initialize database tables"""
        with self.engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
            conn.commit()

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS market_data (
                    id SERIAL,
                    symbol VARCHAR(20) NOT NULL,
                    date TIMESTAMP NOT NULL,
                    open DOUBLE PRECISION,
                    high DOUBLE PRECISION,
                    low DOUBLE PRECISION,
                    close DOUBLE PRECISION,
                    volume BIGINT,
                    source VARCHAR(50),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (symbol, date)
                )
            """))

            try:
                conn.execute(text("""
                    SELECT create_hypertable('market_data', 'date',
                                            if_not_exists => TRUE,
                                            migrate_data => TRUE)
                """))
            except Exception as e:
                logger.info(f"Hypertable already exists or cannot be created: {e}")

            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_market_data_symbol_date
                ON market_data (symbol, date DESC)
            """))

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS tracked_etfs (
                    id SERIAL PRIMARY KEY,
                    symbol VARCHAR(20) UNIQUE NOT NULL,
                    name VARCHAR(200),
                    category VARCHAR(100),
                    leverage_factor FLOAT DEFAULT 1.0,
                    is_inverse BOOLEAN DEFAULT FALSE,
                    is_active BOOLEAN DEFAULT TRUE,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS data_quality (
                    id SERIAL PRIMARY KEY,
                    symbol VARCHAR(20) NOT NULL,
                    date DATE NOT NULL,
                    missing_data BOOLEAN DEFAULT FALSE,
                    data_source VARCHAR(50),
                    quality_score FLOAT,
                    notes TEXT,
                    checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(symbol, date)
                )
            """))

            conn.commit()

        logger.info("Database initialized successfully")

    def store_ohlcv(self, symbol, data):
        """Store OHLCV data to TimescaleDB"""
        try:
            data_to_store = data.copy()
            data_to_store['symbol'] = symbol

            required_columns = ['symbol', 'date', 'open', 'high', 'low', 'close', 'volume']
            data_to_store = data_to_store[required_columns + ['source'] if 'source' in data_to_store.columns else required_columns]

            with self.engine.connect() as conn:
                for _, row in data_to_store.iterrows():
                    conn.execute(text("""
                        INSERT INTO market_data (symbol, date, open, high, low, close, volume, source)
                        VALUES (:symbol, :date, :open, :high, :low, :close, :volume, :source)
                        ON CONFLICT (symbol, date)
                        DO UPDATE SET
                            open = EXCLUDED.open,
                            high = EXCLUDED.high,
                            low = EXCLUDED.low,
                            close = EXCLUDED.close,
                            volume = EXCLUDED.volume,
                            source = EXCLUDED.source
                    """), {
                        'symbol': row['symbol'],
                        'date': row['date'],
                        'open': float(row['open']) if pd.notna(row['open']) else None,
                        'high': float(row['high']) if pd.notna(row['high']) else None,
                        'low': float(row['low']) if pd.notna(row['low']) else None,
                        'close': float(row['close']) if pd.notna(row['close']) else None,
                        'volume': int(row['volume']) if pd.notna(row['volume']) else None,
                        'source': row.get('source', 'Unknown')
                    })
                conn.commit()

            logger.info(f"Stored {len(data_to_store)} rows for {symbol}")

        except Exception as e:
            logger.error(f"Error storing data for {symbol}: {e}")
            raise

    def get_tracked_etfs(self):
        """Get list of tracked ETFs"""
        with self.engine.connect() as conn:
            result = conn.execute(text("""
                SELECT symbol FROM tracked_etfs WHERE is_active = TRUE
            """))
            return [row[0] for row in result]

    def add_tracked_etf(self, symbol, name=None, category=None, leverage_factor=1.0, is_inverse=False):
        """Add ETF to tracking list"""
        with self.engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO tracked_etfs (symbol, name, category, leverage_factor, is_inverse)
                VALUES (:symbol, :name, :category, :leverage_factor, :is_inverse)
                ON CONFLICT (symbol) DO UPDATE SET
                    name = EXCLUDED.name,
                    category = EXCLUDED.category,
                    leverage_factor = EXCLUDED.leverage_factor,
                    is_inverse = EXCLUDED.is_inverse,
                    is_active = TRUE
            """), {
                'symbol': symbol,
                'name': name,
                'category': category,
                'leverage_factor': leverage_factor,
                'is_inverse': is_inverse
            })
            conn.commit()

    def count_historical_data(self):
        """Count total historical records"""
        with self.engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM market_data"))
            return result.scalar()

    def get_data_range(self, symbol):
        """Get date range for a symbol"""
        with self.engine.connect() as conn:
            result = conn.execute(text("""
                SELECT MIN(date) as min_date, MAX(date) as max_date, COUNT(*) as count
                FROM market_data
                WHERE symbol = :symbol
            """), {'symbol': symbol})
            row = result.fetchone()
            return {
                'min_date': row[0],
                'max_date': row[1],
                'count': row[2]
            }

    def get_ohlcv(self, symbol, start_date=None, end_date=None):
        """Retrieve OHLCV data for a symbol"""
        query = "SELECT * FROM market_data WHERE symbol = :symbol"
        params = {'symbol': symbol}

        if start_date:
            query += " AND date >= :start_date"
            params['start_date'] = start_date

        if end_date:
            query += " AND date <= :end_date"
            params['end_date'] = end_date

        query += " ORDER BY date"

        with self.engine.connect() as conn:
            df = pd.read_sql(text(query), conn, params=params)
            return df

    def check_data_quality(self, symbol, date):
        """Check and log data quality issues"""
        with self.engine.connect() as conn:
            result = conn.execute(text("""
                SELECT * FROM market_data
                WHERE symbol = :symbol AND DATE(date) = :date
            """), {'symbol': symbol, 'date': date})

            data = result.fetchone()
            if not data:
                conn.execute(text("""
                    INSERT INTO data_quality (symbol, date, missing_data, quality_score, notes)
                    VALUES (:symbol, :date, TRUE, 0, 'No data found')
                    ON CONFLICT (symbol, date) DO UPDATE SET
                        missing_data = TRUE,
                        quality_score = 0,
                        notes = 'No data found'
                """), {'symbol': symbol, 'date': date})
                conn.commit()
                return 0

            quality_score = 100
            notes = []

            if data['open'] is None or data['close'] is None:
                quality_score -= 50
                notes.append('Missing price data')

            if data['volume'] is None or data['volume'] == 0:
                quality_score -= 20
                notes.append('Missing or zero volume')

            if data['high'] < data['low']:
                quality_score -= 30
                notes.append('High < Low anomaly')

            conn.execute(text("""
                INSERT INTO data_quality (symbol, date, missing_data, data_source, quality_score, notes)
                VALUES (:symbol, :date, FALSE, :source, :score, :notes)
                ON CONFLICT (symbol, date) DO UPDATE SET
                    missing_data = FALSE,
                    data_source = :source,
                    quality_score = :score,
                    notes = :notes
            """), {
                'symbol': symbol,
                'date': date,
                'source': data.get('source', 'Unknown'),
                'score': quality_score,
                'notes': '; '.join(notes) if notes else 'Data OK'
            })
            conn.commit()

            return quality_score