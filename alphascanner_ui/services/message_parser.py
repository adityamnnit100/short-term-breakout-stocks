"""
Service to parse trading signals from text messages.
"""
import re
import pandas as pd


def parse_trade_signal(text: str) -> dict:
    """
    Parses a text message to extract trade signal details using regex.
    
    Returns a dictionary with extracted fields:
    - ticker, signal, entry, stop_loss, targets, pattern
    """
    if not isinstance(text, str):
        return {}

    text = text.upper()
    
    # Regex patterns for various signal components
    # Ticker: Looks for words that look like NSE tickers (e.g., RELIANCE, TATAPOWER.NS)
    ticker_pattern = r'\b([A-Z&]{3,20})(\.NS)?\b'
    
    # Signal: Looks for common buy/sell keywords
    signal_pattern = r'\b(BUY|SELL|BREAKOUT|VCP|ACCUMULATE|SWING)\b'
    
    # Price levels: Looks for numbers after keywords like SL, TGT, etc.
    price_pattern = r'(\d{1,6}(\.\d{1,2})?)'
    sl_pattern = rf'(?:SL|STOP\s*LOSS)\s*:?\s*<?\s*{price_pattern}'
    tgt_pattern = rf'(?:TGT|TARGET)\s*:?\s*>?\s*{price_pattern}'
    entry_pattern = rf'(?:BUY|ENTRY)\s*(?:ABOVE|@|NEAR)?\s*:?\s*{price_pattern}'

    # Find all matches
    tickers = re.findall(ticker_pattern, text)
    signals = re.findall(signal_pattern, text)
    stop_losses = re.findall(sl_pattern, text)
    targets = re.findall(tgt_pattern, text)
    entries = re.findall(entry_pattern, text)

    # Consolidate and clean up results
    # Find the most likely ticker (often the first one mentioned that isn't a signal word)
    found_ticker = None
    for t, _ in tickers:
        if t not in {"BUY", "SELL", "STOP", "LOSS", "TARGET"}:
            found_ticker = t
            break

    # Extract numeric values from tuples returned by re.findall
    sl_values = [float(sl[0]) for sl in stop_losses]
    tgt_values = [float(tgt[0]) for tgt in targets]
    entry_values = [float(e[0]) for e in entries]

    # Determine entry price (CMP if no specific price is mentioned)
    entry_price = entry_values[0] if entry_values else "CMP"
    if 'CMP' in text and not entry_values:
        entry_price = "CMP"

    return {
        "ticker": found_ticker,
        "signal": signals[0] if signals else None,
        "pattern": signals[0] if signals and signals[0] in {"VCP", "BREAKOUT", "SWING"} else None,
        "entry": entry_price,
        "stop_loss": sl_values[0] if sl_values else None,
        "targets": tgt_values,
        "raw_text": text,
    }