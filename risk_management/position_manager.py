"""
Manages open positions, enforces position limits, and tracks PnL.

Fix applied: close_position previously set trade.strategy = position.side
(an OrderSide enum) which is the wrong type — Trade.strategy expects a
StrategyType.  The fix stores strategy_type on Position (added to core/types.py)
and reads it back when constructing the Trade record.

Additional fixes:
- Position notional validation: prevents overleveraged positions that could
  cause liquidation (e.g., 50% of equity on 20x leverage = bankruptcy on 5% move)
- Trade object validation: ensures all required fields are set before recording
- Position size safety checks: validates against min/max order quantities
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
                          entry_price: float, leverage: float,
                          current_equity: float) -> bool:
        """
        Check if a new position can be opened given constraints.
        
        FIX: Now validates notional position size to prevent overleveraging.
        Example: $10k equity, 50% position on 20x = $100k notional = 
        bankruptcy on 10% move. This check prevents that.
        """
        # Check 1: Max open positions count
        open_positions = [p for p in self.positions.values()
                          if p.status == PositionStatus.OPEN]
        if len(open_positions) >= self.config.max_open_positions:
            self.logger.warning(
                f"Max positions reached ({self.config.max_open_positions}), "
                f"currently have {len(open_positions)} open"
            )
            return False

        # Check 2: Already have position for this symbol
        if symbol in self.positions and self.positions[symbol].status == PositionStatus.OPEN:
            self.logger.warning(f"Already have open position for {symbol}")
            return False

        # Check 3: Position size within min/max limits
        if quantity < self.config.min_order_qty:
            self.logger.warning(
                f"Quantity {quantity} below minimum {self.config.min_order_qty}"
            )
            return False
        if quantity > self.config.max_order_qty:
            self.logger.warning(
                f"Quantity {quantity} exceeds maximum {self.config.max_order_qty}"
            )
            return False

        # FIX: Check 4: Position notional value doesn't exceed max_position_pct
        # This prevents leveraged positions from being too large relative to account
        notional_value = quantity * entry_price * leverage
        max_notional = current_equity * self.config.max_position_pct
        
        if notional_value > max_notional:
            self.logger.warning(
                f"Position notional {notional_value:.2f} USDT (qty={quantity} * "
                f"price={entry_price:.2f} * leverage={leverage}) exceeds max "
                f"{max_notional:.2f} USDT ({self.config.max_position_pct:.1%} of equity)"
            )
            risk_logger.log_rejection(
                "Position size exceeds max notional",
                {
                    "symbol": symbol,
                    "notional": notional_value,
                    "max_notional": max_notional,
                    "equity": current_equity,
                    "quantity": quantity,
                    "entry_price": entry_price,
                    "leverage": leverage,
                }
            )
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
        """
        Create and store a new position.
        
        Validates position against all constraints before opening.
        """
        if not self.can_open_position(symbol, side, quantity, entry_price, leverage, current_equity):
            raise PositionRejectedError(
                f"Cannot open {quantity} {symbol} on {side.value}: position violates constraints"
            )

        # Additional validation: SL should be different from entry
        if abs(stop_loss - entry_price) < entry_price * 0.001:
            raise PositionRejectedError(
                f"Stop loss {stop_loss} too close to entry {entry_price} (<0.1%)"
            )

        # Additional validation: TP should be different from entry
        if abs(take_profit - entry_price) < entry_price * 0.001:
            raise PositionRejectedError(
                f"Take profit {take_profit} too close to entry {entry_price} (<0.1%)"
            )

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
        
        notional = quantity * entry_price * leverage
        self.logger.info(
            f"Opened {side.value} {strategy_type.value} position: "
            f"{quantity:.4f} {symbol} @ {entry_price:.2f} "
            f"(notional: {notional:.2f} USDT, {notional/current_equity:.1%} of equity)"
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
        """
        Close a position, record trade, and update daily PnL.
        
        FIX: Validates trade object before recording.
        """
        position = self.positions.get(symbol)
        if not position or position.status != PositionStatus.OPEN:
            self.logger.warning(f"No open position to close for {symbol}")
            return None

        position.close(exit_price, int(datetime.now().timestamp() * 1000))
        pnl = position.realized_pnl
        notional = position.quantity * position.entry_price
        pnl_pct = (pnl / notional * 100) if notional else 0.0

        # FIX: Validate trade object before recording
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
        
        # Validate trade
        if not self._validate_trade(trade):
            self.logger.error(f"Trade validation failed for {symbol}, not recording")
            return None

        self.closed_trades.append(trade)
        self._daily_realized_pnl += pnl

        self.logger.info(
            f"Closed {symbol}: PnL={pnl:.2f} USDT ({pnl_pct:.2f}%) "
            f"Duration={(position.exit_time - position.entry_time)//1000}s"
        )
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

    @staticmethod
    def _validate_trade(trade: Trade) -> bool:
        """
        FIX: Validate trade object has all required fields.
        Prevents invalid trades from being recorded.
        """
        # Check required fields exist
        if not trade.symbol or len(trade.symbol) == 0:
            return False
        if trade.strategy is None:
            return False
        if not isinstance(trade.strategy, StrategyType):
            return False
        if trade.entry_price <= 0 or trade.exit_price <= 0:
            return False
        if trade.quantity <= 0:
            return False
        if trade.timestamp is None or trade.timestamp == 0:
            return False
        # PnL can be negative, so just check it's a number
        if not isinstance(trade.realized_pnl, (int, float)):
            return False
        return True

    def get_open_positions(self) -> List[Position]:
        """Return all currently open positions."""
        return [p for p in self.positions.values() if p.status == PositionStatus.OPEN]

    def get_daily_pnl(self) -> float:
        """Get today's realized profit/loss."""
        return self._daily_realized_pnl

    def reset_daily_pnl(self):
        """Reset daily PnL counter (call at start of new day)."""
        self._daily_realized_pnl = 0.0
