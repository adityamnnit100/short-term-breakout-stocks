"""Watchlist tab UI."""

import pandas as pd
import streamlit as st

from alphascanner_ui.auth import save_current_user_workspace


def render_tab(load_ticker_history) -> None:
    st.markdown('<div class="glass-card"><div class="panel-title" style="color: #00e5ff;">Watchlist</div></div>', unsafe_allow_html=True)

    watchlist = st.session_state.watchlist
    add_symbol = st.text_input("Add Ticker (e.g. RELIANCE.NS)", key="wl_add").upper().strip()
    add_col, _ = st.columns([1, 3])
    with add_col:
        if st.button("➕ Add", key="wl_add_btn") and add_symbol:
            if add_symbol not in watchlist:
                watchlist.append(add_symbol)
                save_current_user_workspace()
                st.success(f"Added {add_symbol}")
            else:
                st.info("Already in watchlist")

    if not watchlist:
        st.info("Your watchlist is empty. Add tickers or scan for signals.")
        return

    watchlist_rows = []
    with st.spinner("Fetching watchlist data…"):
        for ticker in watchlist:
            history = load_ticker_history(ticker, period="5d")
            if history.empty or len(history) < 2:
                continue
            latest_price = float(history["Close"].iloc[-1])
            previous_close = float(history["Close"].iloc[-2])
            change = (latest_price - previous_close) / previous_close * 100
            watchlist_rows.append(
                {
                    "ticker": ticker,
                    "price": latest_price,
                    "change_pct": change,
                    "high": float(history['High'].iloc[-1]),
                    "low": float(history['Low'].iloc[-1]),
                    "volume": int(history['Volume'].iloc[-1]),
                }
            )

    if watchlist_rows:
        df = pd.DataFrame(watchlist_rows)
        st.dataframe(df, use_container_width=True, hide_index=True, column_config={
            "ticker": "Ticker",
            "price": st.column_config.NumberColumn("Price", format="₹%.2f"),
            "change_pct": st.column_config.NumberColumn("Change %", format="%.2f%%"),
            "volume": st.column_config.NumberColumn("Volume", format="%d"),
        })

    remove_symbol = st.selectbox("Remove from watchlist", ["–"] + watchlist, key="wl_rem")
    if remove_symbol != "–" and st.button("❌ Remove", key="wl_rem_btn"):
        st.session_state.watchlist.remove(remove_symbol)
        save_current_user_workspace()
        st.rerun()
