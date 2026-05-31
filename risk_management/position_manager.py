"""
Manages open positions, enforces position limits, and tracks PnL.

Fix applied: close_position previously set trade.strategy = position.side
(an OrderSide enum) which is the wrong type — Trade.strategy expects a
StrategyType.  The fix stores strategy_type on Position (added to core/types.py)
and reads it back when constructing the Trade record.
"""

from typing import List, Dict, Optional
from datetime import datetime

from core.types import Position, OrderSide, PositionStatus, StrategyType, Trade
from core.config import Config
from core.logger import Logger, trade_logger, risk_logger
from core.exceptions import PositionRejectedError


class PositionManager:
    """Track and validate positions."""

    def __init__(self):
        self.config = Config().trading
        self.logger = Logger.get_logger("PositionManager")
        self.positions: Dict[str, Position] = {}   # symbol -> Position
        self.closed_trades: List[Trade] = []
        self._daily_realized_pnl = 0.0

    def can_open_position(self, symbol: str, side: OrderSide, quantity: float,
                          current_equity: float) -> bool:
        """Check if a new position can be opened given constraints."""
        open_positions = [p for p in self.positions.values()
                          if p.status == PositionStatus.OPEN]
        if len(open_positions) >= self.config.max_open_positions:
            self.logger.warning(f"Max positions reached ({self.config.max_open_positions})")
            return False

        if symbol in self.positions and self.positions[symbol].status == PositionStatus.OPEN:
            self.logger.warning(f"Already have open position for {symbol}")
            return False

        return True

    def open_position(
        self,
        symbol: str,
        side: OrderSide,
        entry_price: float,
        quantity: float,
        leverage: float,
        stop_loss: float,
        take_profit: float,
        current_equity: float,
        # FIX: accept strategy_type so it can be stored and later recorded in Trade
        strategy_type: StrategyType = StrategyType.HYBRID,
    ) -> Position:
        """Create and store a new position."""
        if not self.can_open_position(symbol, side, quantity, current_equity):
            raise PositionRejectedError(f"Cannot open position for {symbol}")

        position = Position(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            quantity=quantity,
            leverage=leverage,
            entry_time=int(datetime.now().timestamp() * 1000),
            status=PositionStatus.OPEN,
            strategy_type=strategy_type,  # FIX: store for use in close_position
            stop_loss_price=stop_loss,
            take_profit_price=take_profit,
        )
        self.positions[symbol] = position
        self.logger.info(
            f"Opened {side.value} {strategy_type.value} position: "
            f"{quantity} {symbol} @ {entry_price}"
        )
        trade_logger.log_entry(
            symbol=symbol,
            side=side.value,
            entry_price=entry_price,
            quantity=quantity,
            stop_loss=stop_loss,
            take_profit=take_profit,
            strategy=strategy_type.value,
            reason="Risk approved",
        )
        return position

    def close_position(self, symbol: str, exit_price: float) -> Optional[Trade]:
        """Close a position, record trade, and update daily PnL."""
        position = self.positions.get(symbol)
        if not position or position.status != PositionStatus.OPEN:
            return None

        position.close(exit_price, int(datetime.now().timestamp() * 1000))
        pnl = position.realized_pnl
        notional = position.quantity * position.entry_price
        pnl_pct = (pnl / notional * 100) if notional else 0.0

        trade = Trade(
            timestamp=position.exit_time,
            symbol=symbol,
            # FIX: was position.side (OrderSide), now correctly uses position.strategy_type
            strategy=position.strategy_type,
            side=position.side,
            entry_price=position.entry_price,
            exit_price=exit_price,
            quantity=position.quantity,
            realized_pnl=pnl,
            pnl_percent=pnl_pct,
            duration_seconds=(position.exit_time - position.entry_time) // 1000,
            entry_reason="",
            exit_reason="Stop loss or take profit",
        )
        self.closed_trades.append(trade)
        self._daily_realized_pnl += pnl

        self.logger.info(f"Closed {symbol}: PnL={pnl:.2f} USDT ({pnl_pct:.2f}%)")
        trade_logger.log_exit(
            symbol=symbol,
            side=position.side.value,
            exit_price=exit_price,
            quantity=position.quantity,
            pnl=pnl,
            pnl_pct=pnl_pct,
            reason="SL/TP hit",
        )
        del self.positions[symbol]
        return trade

    def get_open_positions(self) -> List[Position]:
        return [p for p in self.positions.values() if p.status == PositionStatus.OPEN]

    def get_daily_pnl(self) -> float:
        return self._daily_realized_pnl

    def reset_daily_pnl(self):
        self._daily_realized_pnl = 0.0
