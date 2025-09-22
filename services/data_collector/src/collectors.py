import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import requests
import time
import backoff
from alpha_vantage.timeseries import TimeSeries
import logging

logger = logging.getLogger(__name__)


class BaseCollector:
    def __init__(self, priority=1):
        self.priority = priority

    @backoff.on_exception(backoff.expo,
                         (requests.RequestException, ValueError),
                         max_tries=3,
                         max_time=60)
    def fetch_data(self, symbol, start_date=None, end_date=None):
        raise NotImplementedError


class YahooFinanceCollector(BaseCollector):
    def fetch_data(self, symbol, start_date=None, end_date=None):
        """Fetch data from Yahoo Finance"""
        try:
            ticker = yf.Ticker(symbol)

            if start_date and end_date:
                data = ticker.history(start=start_date, end=end_date, interval='1d')
            else:
                data = ticker.history(period='1d')

            if data.empty:
                raise ValueError(f"No data returned for {symbol}")

            data = data.reset_index()
            data['Symbol'] = symbol
            data['Source'] = 'Yahoo Finance'

            data.columns = [col.lower().replace(' ', '_') for col in data.columns]

            required_columns = ['date', 'open', 'high', 'low', 'close', 'volume']
            for col in required_columns:
                if col not in data.columns:
                    raise ValueError(f"Missing required column: {col}")

            return data

        except Exception as e:
            logger.error(f"YahooFinance error for {symbol}: {e}")
            raise


class AlphaVantageCollector(BaseCollector):
    def __init__(self, priority=2, api_key=None):
        super().__init__(priority)
        self.api_key = api_key
        if api_key:
            self.ts = TimeSeries(key=api_key, output_format='pandas')

    def fetch_data(self, symbol, start_date=None, end_date=None):
        """Fetch data from Alpha Vantage"""
        if not self.api_key:
            raise ValueError("Alpha Vantage API key not configured")

        try:
            data, meta_data = self.ts.get_daily(symbol=symbol, outputsize='full')

            data = data.reset_index()
            data.columns = ['date', 'open', 'high', 'low', 'close', 'volume']
            data['symbol'] = symbol
            data['source'] = 'Alpha Vantage'

            if start_date and end_date:
                mask = (data['date'] >= pd.to_datetime(start_date)) & \
                       (data['date'] <= pd.to_datetime(end_date))
                data = data.loc[mask]

            data = data.sort_values('date')

            return data

        except Exception as e:
            logger.error(f"AlphaVantage error for {symbol}: {e}")
            raise


class BackupCollector(BaseCollector):
    def __init__(self, priority=3):
        super().__init__(priority)
        self.base_url = "https://query1.finance.yahoo.com/v8/finance/chart/"

    def fetch_data(self, symbol, start_date=None, end_date=None):
        """Backup collector using direct API calls"""
        try:
            if start_date:
                period1 = int(pd.Timestamp(start_date).timestamp())
            else:
                period1 = int((datetime.now() - timedelta(days=1)).timestamp())

            if end_date:
                period2 = int(pd.Timestamp(end_date).timestamp())
            else:
                period2 = int(datetime.now().timestamp())

            url = f"{self.base_url}{symbol}"
            params = {
                'period1': period1,
                'period2': period2,
                'interval': '1d',
                'events': 'history'
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()
            result = data['chart']['result'][0]

            timestamps = result['timestamp']
            quotes = result['indicators']['quote'][0]

            df = pd.DataFrame({
                'date': pd.to_datetime(timestamps, unit='s'),
                'open': quotes['open'],
                'high': quotes['high'],
                'low': quotes['low'],
                'close': quotes['close'],
                'volume': quotes['volume'],
                'symbol': symbol,
                'source': 'Yahoo API Direct'
            })

            df = df.dropna()

            return df

        except Exception as e:
            logger.error(f"Backup collector error for {symbol}: {e}")
            raise


class PolygonCollector(BaseCollector):
    """Additional data source - Polygon.io (requires API key)"""
    def __init__(self, priority=2, api_key=None):
        super().__init__(priority)
        self.api_key = api_key
        self.base_url = "https://api.polygon.io/v2/aggs/ticker"

    def fetch_data(self, symbol, start_date=None, end_date=None):
        if not self.api_key:
            raise ValueError("Polygon API key not configured")

        try:
            if not start_date:
                start_date = datetime.now() - timedelta(days=1)
            if not end_date:
                end_date = datetime.now()

            start_str = start_date.strftime('%Y-%m-%d')
            end_str = end_date.strftime('%Y-%m-%d')

            url = f"{self.base_url}/{symbol}/range/1/day/{start_str}/{end_str}"
            params = {'apiKey': self.api_key, 'adjusted': 'true'}

            response = requests.get(url, params=params)
            response.raise_for_status()

            data = response.json()

            if 'results' not in data or not data['results']:
                raise ValueError(f"No data returned for {symbol}")

            df = pd.DataFrame(data['results'])
            df['date'] = pd.to_datetime(df['t'], unit='ms')
            df = df.rename(columns={
                'o': 'open',
                'h': 'high',
                'l': 'low',
                'c': 'close',
                'v': 'volume'
            })
            df['symbol'] = symbol
            df['source'] = 'Polygon.io'

            return df[['date', 'open', 'high', 'low', 'close', 'volume', 'symbol', 'source']]

        except Exception as e:
            logger.error(f"Polygon collector error for {symbol}: {e}")
            raise