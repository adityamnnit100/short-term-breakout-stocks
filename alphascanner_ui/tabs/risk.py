"""Risk tab UI."""

import datetime

import pandas as pd
import streamlit as st


def render_tab() -> None:
    st.markdown('<div class="glass-card"><div class="panel-title" style="color: #00e5ff;">Portfolio Risk Management</div></div>', unsafe_allow_html=True)

    input_col_1, input_col_2, input_col_3 = st.columns(3)
    account_size = input_col_1.number_input("Account Size (₹)", 10_000, 100_000_000, 500_000, 10_000, key="rm_acct")
    risk_per_trade = input_col_2.number_input("Risk per Trade (%)", 0.25, 5.0, 1.0, 0.25, key="rm_rpt")
    max_risk_limit = input_col_3.number_input("Max Portfolio Risk (%)", 1.0, 30.0, 5.0, 0.5, key="rm_max")

    positions = st.session_state.portfolio_positions
    total_risk_amount = sum(position.get("risk_amount", 0) for position in positions)
    risk_percent = total_risk_amount / account_size * 100 if account_size > 0 else 0

    metric_col_1, metric_col_2, metric_col_3 = st.columns(3)
    metric_col_1.metric("Total Portfolio Risk", f"₹{total_risk_amount:,.0f}", f"{risk_percent:.1f}%")
    metric_col_2.metric("Remaining Capacity", f"{max(0, max_risk_limit - risk_percent):.1f}%")
    with metric_col_3:
        if risk_percent > max_risk_limit:
            st.error("⚠️ Risk limit exceeded! Stop trading.")
        else:
            st.success("✅ Within risk limits")

    st.divider()
    st.subheader("Position Sizer")

    results = st.session_state.results
    if results is not None and len(results) > 0:
        selected_symbol = st.selectbox("Select stock", results["Ticker"].tolist(), key="rm_sel")
        row = results[results["Ticker"] == selected_symbol].iloc[0]
        entry_price = float(row["LTP"])
        atr = float(row["ATR"])
        stop_loss = entry_price - 1.5 * atr
        risk_amount = account_size * risk_per_trade / 100
        quantity = int(risk_amount // (entry_price - stop_loss)) if (entry_price - stop_loss) > 0 else 0
        total_value = quantity * entry_price

        detail_cols = st.columns(4)
        detail_cols[0].metric("Entry", f"₹{entry_price:.2f}")
        detail_cols[1].metric("Stop Loss", f"₹{stop_loss:.2f}", delta=f"−₹{entry_price - stop_loss:.2f}", delta_color="inverse")
        detail_cols[2].metric("Risk Amount", f"₹{risk_amount:,.0f}")
        detail_cols[3].metric("Shares / Value", f"{quantity} · ₹{total_value:,.0f}")

        if st.button("➕ Add to Portfolio", key="rm_add"):
            st.session_state.portfolio_positions.append(
                {
                    "ticker": selected_symbol,
                    "entry": entry_price,
                    "stop": stop_loss,
                    "shares": quantity,
                    "risk_amount": risk_amount,
                    "total_value": total_value,
                    "date_added": str(datetime.date.today()),
                }
            )
            st.success(f"Added {quantity} × {selected_symbol}")
            st.rerun()

    if not positions:
        return

    st.divider()
    st.subheader("Current Positions")
    st.dataframe(pd.DataFrame(positions), use_container_width=True, hide_index=True)
    remove_position = st.selectbox("Remove", ["–"] + [position["ticker"] for position in positions], key="rm_rem")
    if remove_position != "–" and st.button("❌ Remove", key="rm_rem_btn"):
        st.session_state.portfolio_positions = [
            position for position in positions if position["ticker"] != remove_position
        ]
        st.rerun()
