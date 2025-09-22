.PHONY: help build up down restart logs clean test

help:
	@echo "Available commands:"
	@echo "  make build    - Build all Docker images"
	@echo "  make up       - Start all services"
	@echo "  make down     - Stop all services"
	@echo "  make restart  - Restart all services"
	@echo "  make logs     - View logs"
	@echo "  make clean    - Clean up volumes and images"
	@echo "  make test     - Run tests"
	@echo "  make dev      - Start in development mode"
	@echo "  make prod     - Start in production mode"

build:
	docker-compose build

up:
	docker-compose up -d

down:
	docker-compose down

restart:
	docker-compose down
	docker-compose up -d

logs:
	docker-compose logs -f

clean:
	docker-compose down -v
	docker system prune -af

test:
	docker-compose -f docker-compose.test.yml up --abort-on-container-exit

dev:
	docker-compose -f docker-compose.yml -f docker-compose.dev.yml up

prod:
	docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

db-init:
	docker-compose exec data_collector python -m src.setup

backtest:
	@echo "Running backtest with default parameters..."
	@curl -X POST http://localhost:8001/backtest \
		-H "Content-Type: application/json" \
		-d '{"strategy_name": "momentum", "symbols": ["SPY", "QQQ"], "start_date": "2022-01-01", "end_date": "2023-12-31", "initial_capital": 100000}'

collect-data:
	docker-compose exec data_collector python -c "from src.main import DataCollectorService; service = DataCollectorService(); service.run_daily_collection()"

generate-orders:
	docker-compose exec order_generator python -c "from src.main import OrderGeneratorService; service = OrderGeneratorService(); service.process_end_of_day()"

monitor:
	@echo "Opening monitoring dashboards..."
	@open http://localhost:3000 # Admin UI
	@open http://localhost:15672 # RabbitMQ Management
	@open http://localhost:8000/docs # API Documentation