import os
import sys
import time
import logging
from datetime import datetime, timedelta
import schedule
from concurrent.futures import ThreadPoolExecutor
import json

from .collectors import YahooFinanceCollector, AlphaVantageCollector, BackupCollector
from .database import DatabaseManager
from .message_queue import MessageQueue
from .cache import CacheManager
from .config import Config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DataCollectorService:
    def __init__(self):
        self.config = Config()
        self.db = DatabaseManager(self.config)
        self.mq = MessageQueue(self.config)
        self.cache = CacheManager(self.config)

        self.collectors = [
            YahooFinanceCollector(priority=1),
            AlphaVantageCollector(priority=2),
            BackupCollector(priority=3)
        ]

        self.executor = ThreadPoolExecutor(max_workers=10)

    def collect_etf_data(self, symbols, start_date=None, end_date=None):
        """Collect ETF data with fallback mechanism"""
        results = {}
        failed_symbols = []

        for symbol in symbols:
            cached_data = self.cache.get(f"etf:{symbol}")
            if cached_data and self._is_cache_valid(cached_data):
                results[symbol] = cached_data
                continue

            success = False
            for collector in sorted(self.collectors, key=lambda x: x.priority):
                try:
                    data = collector.fetch_data(symbol, start_date, end_date)
                    if data is not None and not data.empty:
                        results[symbol] = data
                        self.cache.set(f"etf:{symbol}", data, expire=3600)
                        success = True
                        logger.info(f"Successfully collected {symbol} using {collector.__class__.__name__}")
                        break
                except Exception as e:
                    logger.warning(f"Failed to collect {symbol} with {collector.__class__.__name__}: {e}")
                    continue

            if not success:
                failed_symbols.append(symbol)
                logger.error(f"Failed to collect data for {symbol} from all sources")

        if failed_symbols:
            self.mq.publish('failed_collections', {
                'symbols': failed_symbols,
                'timestamp': datetime.now().isoformat()
            })

        return results, failed_symbols

    def _is_cache_valid(self, cached_data):
        """Check if cached data is still valid"""
        if cached_data is None:
            return False
        return True

    def store_data(self, data_dict):
        """Store collected data to database"""
        for symbol, data in data_dict.items():
            try:
                self.db.store_ohlcv(symbol, data)
                self.mq.publish('data_stored', {
                    'symbol': symbol,
                    'rows': len(data),
                    'timestamp': datetime.now().isoformat()
                })
            except Exception as e:
                logger.error(f"Failed to store data for {symbol}: {e}")

    def run_daily_collection(self):
        """Run daily data collection for all tracked ETFs"""
        etf_list = self.db.get_tracked_etfs()

        if not etf_list:
            etf_list = self.config.DEFAULT_ETFS

        logger.info(f"Starting daily collection for {len(etf_list)} ETFs")

        end_date = datetime.now()
        start_date = end_date - timedelta(days=1)

        data, failed = self.collect_etf_data(etf_list, start_date, end_date)
        self.store_data(data)

        self.mq.publish('daily_collection_complete', {
            'total': len(etf_list),
            'success': len(data),
            'failed': len(failed),
            'timestamp': datetime.now().isoformat()
        })

        logger.info(f"Daily collection complete: {len(data)}/{len(etf_list)} successful")

    def run_historical_collection(self, symbols, years=10):
        """Collect historical data for specified symbols"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365 * years)

        logger.info(f"Starting historical collection for {len(symbols)} ETFs ({years} years)")

        batch_size = 10
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i+batch_size]
            data, failed = self.collect_etf_data(batch, start_date, end_date)
            self.store_data(data)
            time.sleep(1)

        logger.info("Historical collection complete")

    def start(self):
        """Start the data collector service"""
        logger.info("Starting Data Collector Service")

        self.db.initialize()

        default_etfs = self.config.DEFAULT_ETFS
        if self.db.count_historical_data() == 0:
            logger.info("No historical data found, initiating historical collection")
            self.run_historical_collection(default_etfs)

        schedule.every().day.at("16:30").do(self.run_daily_collection)
        schedule.every(15).minutes.do(lambda: self.collect_etf_data(
            self.config.REALTIME_ETFS,
            datetime.now() - timedelta(minutes=15),
            datetime.now()
        ))

        while True:
            try:
                schedule.run_pending()
                time.sleep(1)
            except KeyboardInterrupt:
                logger.info("Shutting down Data Collector Service")
                self.executor.shutdown(wait=True)
                break
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}")
                time.sleep(60)


if __name__ == "__main__":
    service = DataCollectorService()
    service.start()