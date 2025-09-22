import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any
import pandas as pd
import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

from .backtester import Backtester
from .metrics import MetricsCalculator
from .visualizer import BacktestVisualizer
from .database import DatabaseManager
from .config import Config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Backtesting Service")


class BacktestRequest(BaseModel):
    strategy_name: str
    symbols: List[str]
    start_date: str
    end_date: str
    initial_capital: float = 100000
    parameters: Dict = {}
    benchmark: str = "SPY"


class BacktestResponse(BaseModel):
    backtest_id: str
    status: str
    metrics: Dict
    trades: List[Dict]
    equity_curve: List[Dict]
    report_url: str


class BacktestingService:
    def __init__(self):
        self.config = Config()
        self.db = DatabaseManager(self.config)
        self.backtester = Backtester()
        self.metrics_calculator = MetricsCalculator()
        self.visualizer = BacktestVisualizer()

    def run_backtest(self, request: BacktestRequest) -> Dict:
        """Run a complete backtest"""
        try:
            market_data = self.db.get_market_data(
                request.symbols,
                request.start_date,
                request.end_date
            )

            if market_data.empty:
                raise ValueError("No market data available for the specified period")

            benchmark_data = self.db.get_market_data(
                [request.benchmark],
                request.start_date,
                request.end_date
            )

            backtest_result = self.backtester.run(
                strategy_name=request.strategy_name,
                market_data=market_data,
                initial_capital=request.initial_capital,
                parameters=request.parameters
            )

            metrics = self.metrics_calculator.calculate(
                backtest_result,
                benchmark_data
            )

            report_url = self.visualizer.create_report(
                backtest_result,
                metrics
            )

            backtest_id = self.db.save_backtest_result(
                request.dict(),
                backtest_result,
                metrics
            )

            return {
                'backtest_id': backtest_id,
                'status': 'completed',
                'metrics': metrics,
                'trades': backtest_result.get('trades', []),
                'equity_curve': backtest_result.get('equity_curve', []),
                'report_url': report_url
            }

        except Exception as e:
            logger.error(f"Backtest failed: {e}")
            raise

    def compare_backtests(self, backtest_ids: List[str]) -> Dict:
        """Compare multiple backtest results"""
        results = []

        for backtest_id in backtest_ids:
            result = self.db.get_backtest_result(backtest_id)
            if result:
                results.append(result)

        if not results:
            raise ValueError("No valid backtest results found")

        comparison = self.metrics_calculator.compare_results(results)

        comparison_report = self.visualizer.create_comparison_report(results)

        return {
            'comparison': comparison,
            'report_url': comparison_report
        }

    def optimize_strategy(self, request: BacktestRequest, param_grid: Dict) -> Dict:
        """Optimize strategy parameters"""
        best_result = None
        best_score = -float('inf')
        all_results = []

        for params in self._generate_param_combinations(param_grid):
            request.parameters = params

            try:
                result = self.run_backtest(request)
                score = result['metrics'].get('sharpe_ratio', 0)

                all_results.append({
                    'parameters': params,
                    'score': score,
                    'metrics': result['metrics']
                })

                if score > best_score:
                    best_score = score
                    best_result = result

            except Exception as e:
                logger.warning(f"Failed with params {params}: {e}")
                continue

        return {
            'best_parameters': best_result['parameters'] if best_result else {},
            'best_score': best_score,
            'best_result': best_result,
            'all_results': all_results
        }

    def _generate_param_combinations(self, param_grid: Dict) -> List[Dict]:
        """Generate parameter combinations for optimization"""
        import itertools

        keys = param_grid.keys()
        values = param_grid.values()

        combinations = []
        for combination in itertools.product(*values):
            combinations.append(dict(zip(keys, combination)))

        return combinations


service = BacktestingService()


@app.post("/backtest", response_model=BacktestResponse)
async def run_backtest(request: BacktestRequest):
    """Run a single backtest"""
    try:
        result = service.run_backtest(request)
        return BacktestResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/compare")
async def compare_backtests(backtest_ids: List[str]):
    """Compare multiple backtests"""
    try:
        result = service.compare_backtests(backtest_ids)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/optimize")
async def optimize_strategy(request: BacktestRequest, param_grid: Dict):
    """Optimize strategy parameters"""
    try:
        result = service.optimize_strategy(request, param_grid)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/backtest/{backtest_id}")
async def get_backtest_result(backtest_id: str):
    """Get backtest result by ID"""
    result = service.db.get_backtest_result(backtest_id)
    if not result:
        raise HTTPException(status_code=404, detail="Backtest not found")
    return result


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)