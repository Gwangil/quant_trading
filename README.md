# Quant Trading System

A comprehensive microservices-based quantitative trading system for US ETFs with multiple investment strategies, risk management, and automated order generation.

## 🎯 Features

### Core Functionality
- **Multi-Portfolio Management**: Run multiple portfolios simultaneously with different risk profiles
- **Multi-Timeframe Strategies**: Automatic repetition based on investment periods (ultra-short to ultra-long)
- **Data Collection**: Multi-source data collection with fallback mechanisms (Yahoo Finance, Alpha Vantage, Polygon.io)
- **Investment Strategies**:
  - Momentum Trading
  - Mean Reversion
  - Machine Learning (ML) Based
  - Trend Following
  - Volatility Trading
  - Pairs Trading
  - Sector Rotation
  - Buy & Hold

### Portfolio Types
1. **Conservative Portfolio**: Safe, long-term focused (40% trend, 30% mean reversion, 30% dividend ETFs)
2. **Balanced Portfolio**: Medium risk/return (25% each: momentum, ML, trend, sector rotation)
3. **Aggressive Portfolio**: High risk/return (30% leveraged momentum, 20% volatility, 50% pairs/ML)
4. **Multi-Timeframe Portfolio**: Mixed periods (15% ultra-short to 15% ultra-long)

### Risk Management
- **Risk Profiles**: 5 levels (Very Safe → Very Risky)
- **Investment Periods**:
  - Ultra Short: 1-5 days
  - Short: 1-4 weeks
  - Medium: 1-3 months
  - Long: 3-12 months
  - Ultra Long: 1+ years
- **Portfolio Optimization**: Dynamic allocation with rebalancing
- **Position Sizing**: Automated based on risk tolerance
- **Stop Loss & Take Profit**: Configurable per strategy

### System Architecture
- **Microservices Architecture**: Docker-based MSA
- **Databases**:
  - PostgreSQL for core data
  - TimescaleDB for time-series market data
  - Redis for caching
- **Message Queue**: RabbitMQ for inter-service communication
- **Real-time Processing**: WebSocket support for live data

## 📦 Services

1. **Data Collector Service**: Fetches and stores market data from multiple sources
2. **Strategy Engine**: Generates trading signals with portfolio management
3. **Backtesting Service**: Tests strategies with historical data and period-based repetition
4. **Order Generator**: Creates daily order sheets
5. **API Gateway**: Central API access point
6. **Admin UI**: Web-based dashboard

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.11+
- Node.js 18+
- (Optional) API keys for data sources

### Installation

1. Clone the repository:
```bash
git clone <repository>
cd quant_strategy
```

2. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configurations
```

3. Configure portfolios (optional):
```bash
# In .env file:
ACTIVE_PORTFOLIOS=Balanced Portfolio,Multi-Timeframe Portfolio
PORTFOLIO_CAPITAL_ALLOCATION=0.5,0.5
```

4. Start all services:
```bash
docker-compose up -d
```

5. Initialize the database:
```bash
make db-init
```

6. Access the Admin UI:
```
http://localhost:3000
```

## 📊 API Endpoints

### Main API Gateway (Port 8000)

- `GET /health` - Health check
- `GET /portfolio` - Current portfolio state
- `GET /portfolios/active` - List active portfolios
- `POST /strategies/run` - Run strategies
- `GET /signals/latest` - Latest trading signals
- `GET /orders/sheet` - Today's order sheet

### Backtesting Service (Port 8001)

- `POST /backtest` - Run backtest with period repetition
- `POST /backtest/multi-period` - Run multi-period backtest
- `POST /optimize` - Optimize strategy parameters
- `GET /backtest/{id}` - Get backtest results
- `POST /compare` - Compare multiple backtest results

## 💹 Multi-Strategy Portfolio Configuration

### Running Multiple Portfolios

Configure in `.env`:
```bash
# Run 2 portfolios simultaneously
ACTIVE_PORTFOLIOS=Balanced Portfolio,Aggressive Portfolio
PORTFOLIO_CAPITAL_ALLOCATION=0.7,0.3  # 70% balanced, 30% aggressive

# Enable multi-period backtesting
ENABLE_MULTI_PERIOD_BACKTEST=true
COMPOUND_RETURNS=true
```

### Strategy Execution Frequency

Each strategy runs based on its investment period:
```bash
ULTRA_SHORT_FREQUENCY=1    # Daily
SHORT_FREQUENCY=3           # Every 3 days
MEDIUM_FREQUENCY=7          # Weekly
LONG_FREQUENCY=14           # Bi-weekly
ULTRA_LONG_FREQUENCY=30     # Monthly
```

### Example: 3-Year Backtest with Period Repetition

```bash
curl -X POST http://localhost:8001/backtest/multi-period \
  -H "Content-Type: application/json" \
  -d '{
    "portfolio_name": "Multi-Timeframe Portfolio",
    "start_date": "2021-01-01",
    "end_date": "2024-01-01",
    "initial_capital": 100000,
    "enable_repetition": true,
    "compound_returns": true
  }'
```

Expected repetitions over 3 years:
- Ultra-short strategies: ~700 times
- Short strategies: ~150 times
- Medium strategies: ~36 times
- Long strategies: ~12 times
- Ultra-long strategies: ~3 times

## 🔧 Configuration

### Risk Profiles Configuration

Each risk profile has different constraints:
```python
# Very Safe: Max 5% per position, no leverage
# Safe: Max 10% per position, no leverage
# Normal: Max 15% per position, 1.5x leverage
# Risky: Max 20% per position, 2x leverage
# Very Risky: Max 30% per position, 3x leverage
```

### Adding Custom Portfolios

Edit `services/strategy_engine/src/config.py`:
```python
DEFAULT_PORTFOLIOS.append({
    'name': 'My Custom Portfolio',
    'strategies': [
        {
            'name': 'my_strategy',
            'type': 'momentum',
            'risk_profile': 'normal',
            'investment_period': 'medium',
            'allocation': 0.5,
            'parameters': {...}
        }
    ]
})
```

## 📈 Backtesting

### Standard Backtest
```bash
make backtest
```

### Multi-Period Backtest with Repetition
```python
# API call
POST /backtest/multi-period
{
    "portfolio_name": "Balanced Portfolio",
    "start_date": "2020-01-01",
    "end_date": "2023-12-31",
    "initial_capital": 100000,
    "enable_repetition": true,  # Short-term strategies repeat
    "compound_returns": true    # Reinvest profits
}
```

### Compare Multiple Strategies
```bash
curl -X POST http://localhost:8001/compare \
  -d '{"backtest_ids": ["id1", "id2", "id3"]}'
```

## 📝 Order Generation

Daily order sheets are generated with portfolio allocation:

```json
{
  "portfolio": "Balanced Portfolio",
  "date": "2024-01-15",
  "orders": [
    {
      "strategy": "momentum_medium",
      "symbol": "SPY",
      "action": "BUY",
      "quantity": 100,
      "allocation": 0.25
    }
  ]
}
```

## 🔒 Security & Risk Management

- **Portfolio-level stop loss**: 15% default
- **Daily loss limit**: 5% default
- **Strategy correlation monitoring**: Alert if >70%
- **Cash reserve**: 5% minimum
- **Dynamic risk adjustment**: Based on market volatility

## 📊 Monitoring & Alerts

### Performance Tracking
- Real-time portfolio value
- Strategy-level P&L
- Risk metrics (Sharpe, Sortino, Max Drawdown)
- Execution statistics per period

### Alert Thresholds
```bash
DRAWDOWN_ALERT_THRESHOLD=-0.1        # 10% drawdown
UNDERPERFORMANCE_THRESHOLD=-0.15     # 15% underperformance
CORRELATION_ALERT=0.9                 # 90% correlation
```

## 🧪 Testing

### Unit Tests
```bash
docker-compose exec strategy_engine pytest
```

### Integration Tests
```bash
docker-compose -f docker-compose.test.yml up
```

### Backtest Validation
```bash
# Run backtest with known data
make test-backtest
```

## 🚢 Production Deployment

1. Update environment variables:
```bash
ENVIRONMENT=production
BROKER_PAPER_TRADING=false  # Enable live trading
```

2. Deploy with production compose:
```bash
docker-compose -f docker-compose.prod.yml up -d
```

3. Set up monitoring:
```bash
PROMETHEUS_ENABLED=true
GRAFANA_ENABLED=true
```

## 📖 Development

### Adding New Strategies

1. Create strategy in `services/strategy_engine/src/strategies/`
2. Inherit from `BaseStrategy`
3. Implement `generate_signals()` method
4. Register in portfolio configuration

### Database Schema

```sql
-- Market Data (TimescaleDB)
CREATE TABLE market_data (
    symbol VARCHAR(20),
    date TIMESTAMP,
    open, high, low, close DOUBLE,
    volume BIGINT
);

-- Portfolio State (PostgreSQL)
CREATE TABLE portfolios (
    id UUID PRIMARY KEY,
    name VARCHAR(100),
    strategies JSONB,
    performance JSONB
);
```

## 🤝 Next Steps for Implementation

### 1. Essential Setup (Do First)
```bash
# 1. Create actual .env file
cp .env.example .env
# Edit with your passwords and API keys

# 2. Get free API keys (recommended):
# - Alpha Vantage: https://www.alphavantage.co/support/#api-key
# - Polygon.io: https://polygon.io (better data quality)

# 3. Build and start services
make build
make up

# 4. Initialize database
make db-init

# 5. Verify services are running
docker-compose ps
```

### 2. Data Collection Setup
```bash
# Test data collection
docker-compose exec data_collector python -c "
from src.main import DataCollectorService
service = DataCollectorService()
service.run_daily_collection()
"

# Check if data is stored
docker-compose exec timescaledb psql -U timescale_user -d market_data \
  -c "SELECT COUNT(*) FROM market_data;"
```

### 3. Strategy Testing
```bash
# Run first backtest
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

### 4. Portfolio Configuration
```bash
# Choose portfolios to run
# Edit .env:
ACTIVE_PORTFOLIOS=Balanced Portfolio
PORTFOLIO_CAPITAL_ALLOCATION=1.0

# Or run multiple:
ACTIVE_PORTFOLIOS=Conservative Portfolio,Aggressive Portfolio
PORTFOLIO_CAPITAL_ALLOCATION=0.7,0.3
```

### 5. Monitoring Setup
```bash
# Access Admin UI
open http://localhost:3000

# Check API documentation
open http://localhost:8000/docs

# Monitor RabbitMQ
open http://localhost:15672
# Username: admin, Password: (from .env)
```

### 6. Testing & Validation
```bash
# Run comprehensive backtest
make test-backtest

# Check system health
curl http://localhost:8000/health
curl http://localhost:8001/health
```

### 7. Production Preparation
- [ ] Set strong passwords in .env
- [ ] Get production API keys
- [ ] Configure SSL certificates
- [ ] Set up backup strategy
- [ ] Configure monitoring alerts
- [ ] Test with paper trading first

## ⚠️ Important Notes

1. **API Keys**: System works without API keys but is more stable with them
2. **Initial Data**: First run downloads 10 years of historical data (may take time)
3. **Paper Trading**: Always test with paper trading before live trading
4. **Backtesting**: Multi-period backtesting gives more realistic results

## 🆘 Troubleshooting

### Common Issues

1. **Services not starting**:
```bash
docker-compose logs -f [service_name]
```

2. **Database connection errors**:
```bash
# Check database is running
docker-compose ps postgres timescaledb

# Restart databases
docker-compose restart postgres timescaledb
```

3. **No market data**:
```bash
# Manually trigger collection
make collect-data
```

4. **Strategy not executing**:
```bash
# Check strategy engine logs
docker-compose logs -f strategy_engine
```

## 📄 License

MIT License

## 🆘 Support

- Issues: GitHub Issues
- Documentation: `/docs` folder
- API Docs: http://localhost:8000/docs (FastAPI Swagger)

## ⚠️ Disclaimer

This system is for educational and research purposes. Always test thoroughly before using with real money. Past performance does not guarantee future results.