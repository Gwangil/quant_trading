import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any
import pandas as pd
import json

from .order_builder import OrderBuilder
from .risk_validator import RiskValidator
from .broker_interface import BrokerInterface
from .database import DatabaseManager
from .message_queue import MessageQueue
from .config import Config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class OrderGeneratorService:
    def __init__(self):
        self.config = Config()
        self.db = DatabaseManager(self.config)
        self.mq = MessageQueue(self.config)
        self.order_builder = OrderBuilder()
        self.risk_validator = RiskValidator(self.config)
        self.broker = BrokerInterface(self.config)

    def generate_orders(self, signals: List[Dict], portfolio_state: Dict) -> List[Dict]:
        """Generate orders from trading signals"""
        orders = []

        for signal in signals:
            order = self.order_builder.build_order(signal, portfolio_state)

            is_valid, reason = self.risk_validator.validate_order(order, portfolio_state)
            if not is_valid:
                logger.warning(f"Order rejected for {order['symbol']}: {reason}")
                continue

            order = self.risk_validator.apply_risk_limits(order, portfolio_state)

            orders.append(order)

        return orders

    def process_end_of_day(self):
        """Process end-of-day to generate next day orders"""
        try:
            latest_signals = self.db.get_latest_signals()
            portfolio_state = self.db.get_portfolio_state()

            if not latest_signals:
                logger.info("No signals available for order generation")
                return

            orders = self.generate_orders(latest_signals, portfolio_state)

            order_sheet = self.create_order_sheet(orders)

            self.db.save_order_sheet(order_sheet)

            self.mq.publish('orders_generated', {
                'order_count': len(orders),
                'total_value': sum(o.get('estimated_value', 0) for o in orders),
                'timestamp': datetime.now().isoformat()
            })

            logger.info(f"Generated {len(orders)} orders for next trading day")

            return order_sheet

        except Exception as e:
            logger.error(f"Error in end-of-day processing: {e}")
            raise

    def create_order_sheet(self, orders: List[Dict]) -> Dict:
        """Create order sheet for next trading day"""
        order_sheet = {
            'generated_at': datetime.now().isoformat(),
            'trading_date': (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d'),
            'orders': [],
            'summary': {
                'total_orders': len(orders),
                'buy_orders': 0,
                'sell_orders': 0,
                'total_buy_value': 0,
                'total_sell_value': 0
            }
        }

        for order in orders:
            formatted_order = {
                'symbol': order['symbol'],
                'action': order['action'],
                'order_type': order.get('order_type', 'MARKET'),
                'quantity': order['quantity'],
                'limit_price': order.get('limit_price'),
                'stop_price': order.get('stop_price'),
                'time_in_force': order.get('time_in_force', 'DAY'),
                'estimated_value': order.get('estimated_value', 0),
                'strategy': order.get('strategy'),
                'confidence': order.get('confidence'),
                'notes': order.get('notes', '')
            }

            order_sheet['orders'].append(formatted_order)

            if order['action'] == 'BUY':
                order_sheet['summary']['buy_orders'] += 1
                order_sheet['summary']['total_buy_value'] += order.get('estimated_value', 0)
            else:
                order_sheet['summary']['sell_orders'] += 1
                order_sheet['summary']['total_sell_value'] += order.get('estimated_value', 0)

        return order_sheet

    def execute_orders(self, order_sheet: Dict, live_trading: bool = False):
        """Execute orders (paper trading or live)"""
        results = []

        for order in order_sheet['orders']:
            try:
                if live_trading and self.broker.is_connected():
                    result = self.broker.place_order(order)
                else:
                    result = self.simulate_order_execution(order)

                results.append(result)

                self.db.save_order_execution(order, result)

            except Exception as e:
                logger.error(f"Failed to execute order for {order['symbol']}: {e}")
                results.append({
                    'symbol': order['symbol'],
                    'status': 'FAILED',
                    'error': str(e)
                })

        return results

    def simulate_order_execution(self, order: Dict) -> Dict:
        """Simulate order execution for paper trading"""
        return {
            'symbol': order['symbol'],
            'action': order['action'],
            'quantity': order['quantity'],
            'status': 'SIMULATED',
            'executed_price': order.get('limit_price', 0),
            'executed_at': datetime.now().isoformat(),
            'order_id': f"SIM_{order['symbol']}_{datetime.now().timestamp()}"
        }

    def start(self):
        """Start the order generator service"""
        logger.info("Starting Order Generator Service")

        self.db.initialize()

        def handle_signal_update(message):
            try:
                signals = message.get('signals', [])
                portfolio_state = self.db.get_portfolio_state()
                orders = self.generate_orders(signals, portfolio_state)

                if orders:
                    order_sheet = self.create_order_sheet(orders)
                    self.db.save_order_sheet(order_sheet)

            except Exception as e:
                logger.error(f"Error handling signal update: {e}")

        self.mq.consume('signals', handle_signal_update)


if __name__ == "__main__":
    service = OrderGeneratorService()
    service.start()