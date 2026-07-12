"""Shared threading utilities to prevent circular imports."""
import threading

_YFINANCE_LOCK = threading.Lock()