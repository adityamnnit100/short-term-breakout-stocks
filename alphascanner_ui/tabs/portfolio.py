"""User-specific multi-account portfolio tab."""

import datetime
from typing import Dict, List

import pandas as pd
import streamlit as st

from breakout import calculate_atr, calculate_macd, calculate_rsi
from alphascanner_ui.auth import save_current_user_workspace


def _normalise_ticker(ticker: str) -> str:
    ticker = ticker.upper().strip()
    if ticker and "." not in ticker:
        ticker = f"{ticker}.NS"
    return ticker


def _get_portfolios() -> List[Dict]:
    portfolios = st.session_state.setdefault("portfolios", [])
    if not isinstance(portfolios, list):
        portfolios = []
        st.session_state.portfolios = portfolios
    return portfolios


def _analyse_holding(holding: Dict, load_ticker_history) -> Dict:
    ticker = holding.get("ticker", "")
    history = load_ticker_history(ticker, period="1y")
    if history.empty or len(history) < 60:
        return {
            "Ticker": ticker,
            "Qty": holding.get("quantity", 0),
            "Avg Price": holding.get("avg_price", 0.0),
            "LTP": None,
            "P&L %": None,
            "RSI": None,
            "Trend": "No data",
            "Momentum": "No data",
            "Signal": "WAIT",
            "Reason": "Not enough price history to analyse.",
        }

    close = history["Close"]
    high = history["High"]
    low = history["Low"]
    ltp = float(close.iloc[-1])
    avg_price = float(holding.get("avg_price", 0.0) or 0.0)
    pnl_pct = (ltp - avg_price) / avg_price * 100 if avg_price > 0 else 0.0
    sma20 = float(close.rolling(20).mean().iloc[-1])
    sma50 = float(close.rolling(50).mean().iloc[-1])
    sma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else sma50
    rsi = float(calculate_rsi(close).iloc[-1])
    macd, macd_signal, _ = calculate_macd(close)
    macd_is_bullish = float(macd.iloc[-1]) >= float(macd_signal.iloc[-1])
    atr = float(calculate_atr(high, low, close).iloc[-1])
    if pd.isna(rsi):
        rsi = 50.0
    if pd.isna(atr) or atr <= 0:
        atr = ltp * 0.015

    above_20 = ltp >= sma20
    above_50 = ltp >= sma50
    above_200 = ltp >= sma200
    trend_up = above_20 and above_50 and above_200
    trend_down = ltp < sma50 and not macd_is_bullish
    stop_zone = avg_price > 0 and ltp < max(avg_price - 1.5 * atr, sma50 * 0.98)

    if trend_up and macd_is_bullish and 45 <= rsi <= 72:
        signal = "HOLD"
        reason = "Trend is healthy: price is above key averages with bullish momentum."
    elif trend_down and (rsi < 45 or stop_zone):
        signal = "SELL"
        reason = "Weak setup: price is below SMA50 with bearish momentum or near the risk zone."
    elif rsi > 78:
        signal = "WAIT"
        reason = "Stock is extended. Avoid adding; trail stops or wait for a cool-off."
    elif not above_20 or not macd_is_bullish:
        signal = "WAIT"
        reason = "Momentum is mixed. Hold only with a clear stop; wait before adding."
    else:
        signal = "HOLD"
        reason = "Setup is acceptable but not a fresh breakout."

    trend = "Uptrend" if trend_up else ("Weak" if trend_down else "Mixed")
    momentum = "Bullish" if macd_is_bullish else "Bearish"

    return {
        "Ticker": ticker,
        "Qty": int(holding.get("quantity", 0) or 0),
        "Avg Price": avg_price,
        "LTP": ltp,
        "P&L %": pnl_pct,
        "RSI": rsi,
        "Trend": trend,
        "Momentum": momentum,
        "Signal": signal,
        "Reason": reason,
    }


def _render_analysis(portfolio: Dict, load_ticker_history) -> None:
    holdings = portfolio.get("holdings", [])
    if not holdings:
        st.info("Add stocks before running analysis.")
        return

    with st.spinner(f"Analysing {portfolio['name']} holdings..."):
        rows = [_analyse_holding(holding, load_ticker_history) for holding in holdings]

    df = pd.DataFrame(rows)
    valid_prices = df.dropna(subset=["LTP"])
    total_value = 0.0
    total_cost = 0.0
    if not valid_prices.empty:
        total_value = float((valid_prices["LTP"] * valid_prices["Qty"]).sum())
        total_cost = float((valid_prices["Avg Price"] * valid_prices["Qty"]).sum())
    total_pnl_pct = (total_value - total_cost) / total_cost * 100 if total_cost > 0 else 0.0

    metric_cols = st.columns(4)
    metric_cols[0].metric("Holdings", len(holdings))
    metric_cols[1].metric("Current Value", f"₹{total_value:,.0f}")
    metric_cols[2].metric("P&L", f"{total_pnl_pct:.1f}%")
    metric_cols[3].metric("Sell Alerts", int((df["Signal"] == "SELL").sum()))

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Avg Price": st.column_config.NumberColumn("Avg Price", format="₹%.2f"),
            "LTP": st.column_config.NumberColumn("LTP", format="₹%.2f"),
            "P&L %": st.column_config.NumberColumn("P&L %", format="%.2f%%"),
            "RSI": st.column_config.NumberColumn("RSI", format="%.1f"),
        },
    )


def _render_portfolio_tab(index: int, portfolio: Dict, load_ticker_history) -> None:
    holdings = portfolio.setdefault("holdings", [])

    st.subheader(str(portfolio["name"]))
    add_col_1, add_col_2, add_col_3, add_col_4 = st.columns([1.5, 1, 1, 1])
    ticker = _normalise_ticker(add_col_1.text_input("Ticker", key=f"pf_ticker_{index}", placeholder="RELIANCE or RELIANCE.NS"))
    quantity = add_col_2.number_input("Quantity", min_value=1, step=1, key=f"pf_qty_{index}")
    avg_price = add_col_3.number_input("Avg Buy Price", min_value=0.0, step=0.05, key=f"pf_avg_{index}")
    with add_col_4:
        st.write("")
        st.write("")
        if st.button("Add Stock", key=f"pf_add_{index}", use_container_width=True):
            if not ticker:
                st.error("Enter a ticker.")
            else:
                existing = next((row for row in holdings if row.get("ticker") == ticker), None)
                if existing:
                    existing["quantity"] = int(quantity)
                    existing["avg_price"] = float(avg_price)
                    existing["updated_at"] = str(datetime.date.today())
                else:
                    holdings.append(
                        {
                            "ticker": ticker,
                            "quantity": int(quantity),
                            "avg_price": float(avg_price),
                            "date_added": str(datetime.date.today()),
                        }
                    )
                save_current_user_workspace()
                st.success(f"Saved {ticker}.")
                st.rerun()

    if holdings:
        holdings_df = pd.DataFrame(holdings)
        st.dataframe(
            holdings_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "ticker": "Ticker",
                "quantity": "Qty",
                "avg_price": st.column_config.NumberColumn("Avg Price", format="₹%.2f"),
            },
        )

        remove_ticker = st.selectbox(
            "Remove stock",
            ["-"] + [holding["ticker"] for holding in holdings],
            key=f"pf_remove_{index}",
        )
        action_col_1, action_col_2 = st.columns(2)
        with action_col_1:
            if st.button("Analyse", key=f"pf_analyse_{index}", use_container_width=True):
                st.session_state[f"portfolio_analysis_{index}"] = True
        with action_col_2:
            if remove_ticker != "-" and st.button("Remove Stock", key=f"pf_remove_btn_{index}", use_container_width=True):
                portfolio["holdings"] = [holding for holding in holdings if holding["ticker"] != remove_ticker]
                save_current_user_workspace()
                st.rerun()

        if st.session_state.get(f"portfolio_analysis_{index}"):
            _render_analysis(portfolio, load_ticker_history)
    else:
        st.info("No stocks added yet.")


def render_tab(load_ticker_history) -> None:
    st.markdown(
        '<div class="glass-card"><div class="panel-title" style="color: #00e5ff;">Portfolio</div>'
        '<p style="color:#cbd5e1;margin:0;">Create separate broker/account sections and analyse holdings independently.</p></div>',
        unsafe_allow_html=True,
    )

    portfolios = _get_portfolios()

    with st.expander("Create Portfolio", expanded=not portfolios):
        col_1, col_2 = st.columns([2, 1])
        portfolio_name = col_1.text_input("Portfolio name", placeholder="Zerodha, Upstox, Long Term, Swing", key="pf_new_name")
        with col_2:
            st.write("")
            st.write("")
            if st.button("Create", use_container_width=True, key="pf_create"):
                clean_name = portfolio_name.strip()
                if not clean_name:
                    st.error("Enter a portfolio name.")
                elif any(portfolio.get("name", "").lower() == clean_name.lower() for portfolio in portfolios):
                    st.error("A portfolio with this name already exists.")
                else:
                    portfolios.append({"name": clean_name, "holdings": []})
                    save_current_user_workspace()
                    st.success(f"Created {clean_name}.")
                    st.rerun()

    if not portfolios:
        st.info("Create your first portfolio, for example Zerodha or Upstox.")
        return

    tab_labels = [portfolio.get("name", f"Portfolio {i + 1}") for i, portfolio in enumerate(portfolios)]
    tabs = st.tabs(tab_labels)
    for index, (tab, portfolio) in enumerate(zip(tabs, portfolios)):
        with tab:
            _render_portfolio_tab(index, portfolio, load_ticker_history)

            st.divider()
            if st.button("Delete This Portfolio", key=f"pf_delete_{index}"):
                portfolios.pop(index)
                save_current_user_workspace()
                st.rerun()
