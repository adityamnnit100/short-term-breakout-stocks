"""Watchlist tab UI."""

import pandas as pd
import streamlit as st

from alphascanner_ui.auth import save_current_user_workspace


def render_tab(load_ticker_history) -> None:
    st.markdown('<div class="glass-card"><div class="panel-title" style="color: #00e5ff;">Watchlist Management</div></div>', unsafe_allow_html=True)

    if isinstance(st.session_state.get("watchlist"), list):
        st.session_state.watchlist = {"Default": st.session_state.watchlist}
    elif not isinstance(st.session_state.get("watchlist"), dict):
        st.session_state.watchlist = {"Default": []}

    watchlist = st.session_state.watchlist

    # 1. Category Management (Add/Delete Lists)
    with st.expander("📁 Manage List Categories", expanded=False):
        c1, c2 = st.columns([2, 1])
        new_cat = c1.text_input("New List Name", key="wl_new_cat_name", placeholder="e.g. High Momentum")
        if c2.button("➕ Create List", use_container_width=True):
            name = new_cat.strip()
            if name and name not in watchlist:
                watchlist[name] = []
                save_current_user_workspace()
                st.rerun()

        del_options = [k for k in watchlist.keys() if k != "Default"]
        if del_options:
            del_cat = st.selectbox("Delete Entire List", options=["--"] + del_options)
            if del_cat != "--" and st.button("🗑️ Confirm Delete", type="primary", use_container_width=True):
                del watchlist[del_cat]
                save_current_user_workspace()
                st.rerun()

    if not watchlist:
        st.info("Your watchlist store is empty.")
        return

    # 2. Render Tabs for each Watchlist Category
    cat_names = list(watchlist.keys())
    tabs = st.tabs(cat_names)

    for i, cat_name in enumerate(cat_names):
        with tabs[i]:
            tickers = watchlist[cat_name]

            # Add Ticker specific to this list
            add_col, _ = st.columns([1, 1.5])
            add_symbol = add_col.text_input(f"Add Ticker to {cat_name}", key=f"wl_add_{cat_name}").upper().strip()
            if add_symbol and add_col.button(f"➕ Add to {cat_name}", key=f"wl_btn_{cat_name}"):
                if add_symbol not in tickers:
                    tickers.append(add_symbol)
                    save_current_user_workspace()
                    st.rerun()
                else:
                    st.info(f"{add_symbol} is already in '{cat_name}'")

            if not tickers:
                st.info(f"The list '{cat_name}' is currently empty.")
                continue

            # Fetch and display data for tickers in this category
            watchlist_rows = []
            with st.spinner(f"Fetching {cat_name} data…"):
                for ticker in tickers:
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
            else:
                st.warning("No data available for tickers in this list.")

            # Removal Logic for this specific category
            rem_col1, _ = st.columns([1, 1.5])
            remove_symbol = rem_col1.selectbox("Remove from list", ["–"] + tickers, key=f"wl_rem_{cat_name}")
            if remove_symbol != "–" and rem_col1.button("❌ Remove Ticker", key=f"wl_rem_btn_{cat_name}"):
                tickers.remove(remove_symbol)
                save_current_user_workspace()
                st.rerun()
