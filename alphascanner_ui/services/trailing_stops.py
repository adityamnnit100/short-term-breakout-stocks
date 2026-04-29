"""Trailing stops manager for position management."""

import pandas as pd
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class TrailingStop:
    """Represents a single trailing stop position."""
    
    def __init__(self, ticker: str, entry_price: float, quantity: int, 
                 atr_multiplier: float = 1.5, max_profit_pct: Optional[float] = None):
        """Initialize trailing stop.
        
        Args:
            ticker: Stock ticker
            entry_price: Entry price
            quantity: Quantity held
            atr_multiplier: ATR multiplier for stop calculation (default 1.5)
            max_profit_pct: Max profit to lock in before trailing (optional)
        """
        self.ticker = ticker
        self.entry_price = entry_price
        self.quantity = quantity
        self.atr_multiplier = atr_multiplier
        self.max_profit_pct = max_profit_pct
        self.highest_price = entry_price
        self.trailing_stop = entry_price
        self.locked_in_profit = 0.0
        self.created_at = datetime.now()
        self.stopped_out = False
    
    def update(self, current_price: float, atr: float) -> Dict:
        """Update trailing stop based on current price and ATR.
        
        Args:
            current_price: Current market price
            atr: Current ATR value
            
        Returns:
            Dict with state: {price, stop, trail_amount, pnl, pnl_pct, status}
        """
        if self.stopped_out:
            return self._get_state(current_price, atr)
        
        # Update highest price
        if current_price > self.highest_price:
            self.highest_price = current_price
        
        # Calculate new trailing stop (ATR-based)
        new_stop = self.highest_price - (atr * self.atr_multiplier)
        
        # Lock in profit if max_profit_pct is hit
        if self.max_profit_pct is not None:
            max_price_allowed = self.entry_price * (1 + self.max_profit_pct / 100)
            if self.highest_price >= max_price_allowed:
                # Lock in at least the max_profit_pct as minimum stop
                new_stop = max(new_stop, self.entry_price * (1 + (self.max_profit_pct / 100) * 0.5))
                self.locked_in_profit = (self.highest_price - self.entry_price) * self.quantity
        
        # Update trailing stop (never lower)
        if new_stop > self.trailing_stop:
            self.trailing_stop = new_stop
        
        # Check if stopped out
        if current_price <= self.trailing_stop:
            self.stopped_out = True
            logger.info(f"Stopped out: {self.ticker} at ₹{current_price:.2f}")
        
        return self._get_state(current_price, atr)
    
    def _get_state(self, current_price: float, atr: float) -> Dict:
        """Get current state of trailing stop.
        
        Args:
            current_price: Current price
            atr: Current ATR
            
        Returns:
            State dictionary
        """
        pnl = (current_price - self.entry_price) * self.quantity
        pnl_pct = ((current_price - self.entry_price) / self.entry_price) * 100 if self.entry_price > 0 else 0
        trail_amount = self.highest_price - self.trailing_stop
        
        return {
            "ticker": self.ticker,
            "entry_price": self.entry_price,
            "current_price": current_price,
            "quantity": self.quantity,
            "highest_price": self.highest_price,
            "trailing_stop": self.trailing_stop,
            "trail_amount": trail_amount,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "atr": atr,
            "status": "STOPPED_OUT" if self.stopped_out else ("ACTIVE" if current_price > self.trailing_stop else "AT_RISK"),
            "locked_in_profit": self.locked_in_profit,
            "distance_to_stop": current_price - self.trailing_stop,
        }


class TrailingStopsManager:
    """Manager for multiple trailing stop positions."""
    
    def __init__(self):
        """Initialize trailing stops manager."""
        self.positions: Dict[str, TrailingStop] = {}
    
    def add_position(self, ticker: str, entry_price: float, quantity: int,
                    atr_multiplier: float = 1.5, max_profit_pct: Optional[float] = None):
        """Add a position to track with trailing stop.
        
        Args:
            ticker: Stock ticker
            entry_price: Entry price
            quantity: Quantity
            atr_multiplier: ATR multiplier
            max_profit_pct: Max profit to lock in
        """
        key = f"{ticker}_{entry_price}_{quantity}"
        self.positions[key] = TrailingStop(ticker, entry_price, quantity, atr_multiplier, max_profit_pct)
        logger.info(f"Added trailing stop: {ticker} @ ₹{entry_price:.2f}, Qty: {quantity}")
    
    def remove_position(self, ticker: str, entry_price: float, quantity: int):
        """Remove a position from tracking.
        
        Args:
            ticker: Stock ticker
            entry_price: Entry price
            quantity: Quantity
        """
        key = f"{ticker}_{entry_price}_{quantity}"
        if key in self.positions:
            del self.positions[key]
            logger.info(f"Removed trailing stop: {ticker}")
    
    def update_all(self, price_data: pd.DataFrame, atr_data: pd.DataFrame) -> Dict[str, Dict]:
        """Update all trailing stop positions.
        
        Args:
            price_data: DataFrame with current prices (index: ticker, column: 'Close')
            atr_data: DataFrame with ATR values (index: ticker, column: 'ATR')
            
        Returns:
            Dictionary of states keyed by ticker
        """
        states = {}
        
        for key, position in self.positions.items():
            ticker = position.ticker
            
            if ticker not in price_data.index or ticker not in atr_data.index:
                continue
            
            current_price = price_data.loc[ticker, 'Close']
            atr = atr_data.loc[ticker, 'ATR']
            
            state = position.update(current_price, atr)
            states[ticker] = state
        
        return states
    
    def get_active_positions(self) -> List[Dict]:
        """Get all active (non-stopped) positions.
        
        Returns:
            List of active position states
        """
        return [
            pos._get_state(pos.highest_price, 0) 
            for pos in self.positions.values() 
            if not pos.stopped_out
        ]
    
    def get_stopped_out_positions(self) -> List[Dict]:
        """Get all stopped-out positions.
        
        Returns:
            List of stopped-out position states
        """
        return [
            pos._get_state(pos.trailing_stop, 0) 
            for pos in self.positions.values() 
            if pos.stopped_out
        ]
    
    def get_at_risk_positions(self, threshold_pct: float = 2.0) -> List[Dict]:
        """Get positions at risk (close to stop).
        
        Args:
            threshold_pct: Percentage from stop to consider at risk
            
        Returns:
            List of at-risk position states
        """
        at_risk = []
        
        for pos in self.positions.values():
            if pos.stopped_out:
                continue
            
            distance_pct = ((pos.highest_price - pos.trailing_stop) / pos.trailing_stop) * 100
            
            if distance_pct <= threshold_pct:
                at_risk.append(pos._get_state(pos.highest_price, 0))
        
        return at_risk
    
    def get_summary(self) -> Dict:
        """Get summary of all positions.
        
        Returns:
            Summary dictionary with totals and stats
        """
        active = self.get_active_positions()
        stopped = self.get_stopped_out_positions()
        at_risk = self.get_at_risk_positions()
        
        total_pnl = sum(pos["pnl"] for pos in active) + sum(pos["pnl"] for pos in stopped)
        total_positions = len(self.positions)
        
        return {
            "total_positions": total_positions,
            "active_positions": len(active),
            "stopped_out": len(stopped),
            "at_risk": len(at_risk),
            "total_pnl": total_pnl,
            "active": active,
            "stopped": stopped,
            "at_risk": at_risk,
        }
    
    def get_position_state(self, ticker: str, current_price: float, atr: float) -> Optional[Dict]:
        """Get state of a specific position.
        
        Args:
            ticker: Stock ticker
            current_price: Current price
            atr: Current ATR
            
        Returns:
            Position state or None if not found
        """
        for pos in self.positions.values():
            if pos.ticker == ticker and not pos.stopped_out:
                return pos._get_state(current_price, atr)
        
        return None
