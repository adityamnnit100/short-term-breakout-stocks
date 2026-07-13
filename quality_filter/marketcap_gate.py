"""Market-cap gate for the quality filter."""

from __future__ import annotations

from typing import Optional

from .models import GateResult, QualityContext, QualityGate


class MarketCapGate(QualityGate):
    name = "market_cap"

    def evaluate(self, context: QualityContext) -> GateResult:
        mode = str(context.market_cap_mode or context.config.quality_market_cap_mode or "Custom")
        custom_symbols = context.market_cap_custom_symbols or context.config.quality_market_cap_custom_symbols or []

        if mode.lower() == "custom" and custom_symbols:
            if context.ticker not in custom_symbols:
                return GateResult(name=self.name, passed=False, reason="Market Cap Universe Rejected", detail={"mode": mode})

        min_cap = float(context.config.quality_min_market_cap_cr)
        max_cap = float(context.config.quality_max_market_cap_cr)
        market_cap_cr = float(context.market_cap_cr or 0.0)

        if min_cap > 0 and market_cap_cr > 0 and market_cap_cr < min_cap:
            return GateResult(
                name=self.name,
                passed=False,
                reason="Market Cap Below Minimum",
                detail={"market_cap_cr": round(market_cap_cr, 2), "min_market_cap_cr": round(min_cap, 2)},
            )
        if max_cap > 0 and market_cap_cr > max_cap:
            return GateResult(
                name=self.name,
                passed=False,
                reason="Market Cap Above Maximum",
                detail={"market_cap_cr": round(market_cap_cr, 2), "max_market_cap_cr": round(max_cap, 2)},
            )
        return GateResult(
            name=self.name,
            passed=True,
            detail={"market_cap_cr": round(market_cap_cr, 2), "mode": mode},
        )


def get_market_cap_cr_quietly(ticker: str) -> float:
    """Fetch market cap in crores without noisy logging."""
    try:
        import yfinance as yf

        market_ticker = yf.Ticker(ticker)
        market_cap = 0.0
        try:
            market_cap = market_ticker.fast_info.get("marketCap", 0)  # type: ignore[attr-defined]
        except Exception:
            market_cap = getattr(market_ticker, "info", {}).get("marketCap", 0) if hasattr(market_ticker, "info") else 0
        return float(market_cap or 0.0) / 10_000_000
    except Exception:
        return 0.0
