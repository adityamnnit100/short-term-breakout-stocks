"""Backtest tab UI."""

import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def render_tab(settings, run_backtest_cached, load_nifty_history) -> None:
    st.markdown(
        '<div class="glass-card"><div class="panel-title">Strategy Back-test</div><p style="color:#8899bb;margin:0;">Validates signal quality using 1:2 risk-reward (SL = 1.5×ATR, TP = 3×ATR)</p></div>',
        unsafe_allow_html=True,
    )

    column_1, column_2, column_3 = st.columns([1, 1, 1])
    start_date = column_1.date_input("Start Date", datetime.date.today() - datetime.timedelta(days=60))
    end_date = column_2.date_input("End Date", datetime.date.today())
    with column_3:
        st.write("")
        st.write("")
        run_backtest = st.button("🚀 Run Backtest", use_container_width=True)

    if run_backtest:
        with st.spinner("Analysing 2 years of historical data…"):
            bt_df, error = run_backtest_cached(
                start_date=start_date,
                end_date=end_date,
                vol_thresh=settings.vol_thresh,
                rsi_min=settings.rsi_range[0],
                rsi_max=settings.rsi_range[1],
                dist_thresh=settings.dist_thresh,
            )
        if error:
            st.error(f"❌ {error}")
        else:
            st.session_state.bt_results = bt_df

    if st.session_state.bt_results is None:
        return

    bt_df = st.session_state.bt_results
    if bt_df.empty:
        st.info("No signals found for the selected date range and parameters.")
        return

    bt_df = bt_df.copy()
    if "PnL_R" not in bt_df.columns:
        bt_df["PnL_R"] = bt_df["Outcome"].map({"Win": 2.0, "Loss": -1.0}).fillna(0)

    completed = bt_df[bt_df["Outcome"] != "Pending"].copy()
    wins = int((completed["Outcome"] == "Win").sum())
    losses = int((completed["Outcome"] == "Loss").sum())
    expired = int((completed["Outcome"] == "Expired").sum())
    total = len(completed)
    pending = int((bt_df["Outcome"] == "Pending").sum())
    win_rate = wins / total * 100 if total > 0 else 0
    realized_r = float(completed["PnL_R"].fillna(0).sum()) if total > 0 else 0.0
    expectancy = realized_r / total if total > 0 else 0.0

    metrics = st.columns(6)
    metrics[0].metric("Total Signals", len(bt_df))
    metrics[1].metric("Completed", total)
    metrics[2].metric("Win Rate", f"{win_rate:.1f}%")
    metrics[3].metric("Expectancy", f"{expectancy:+.2f}R")
    metrics[4].metric("Realized R", f"{realized_r:+.1f}R")
    metrics[5].metric("Pending", pending)
    st.metric("Wins / Losses / Expired", f"{wins} / {losses} / {expired}")

    nifty = load_nifty_history(period="2y")
    if not nifty.empty:
        min_date = pd.to_datetime(bt_df["Date"].min())
        max_date = pd.to_datetime(bt_df["Date"].max())
        if "Exit_Date" in bt_df and not bt_df["Exit_Date"].dropna().empty:
            max_date = max(max_date, pd.to_datetime(bt_df["Exit_Date"].dropna().max()))
        filtered_nifty = nifty[(nifty.index >= min_date) & (nifty.index <= max_date)]
        if len(filtered_nifty) >= 2:
            nifty_return = (float(filtered_nifty["Close"].iloc[-1]) / float(filtered_nifty["Close"].iloc[0]) - 1) * 100
            alpha_cols = st.columns(3)
            alpha_cols[0].metric("Strategy P&L", f"{realized_r:+.1f}R")
            alpha_cols[1].metric("Nifty 50 Return", f"{nifty_return:+.1f}%")
            alpha_cols[2].metric("Avg R / Completed", f"{expectancy:+.2f}R")

    st.divider()
    bt_sorted = bt_df.sort_values("Date").copy()
    bt_sorted["PnL_R"] = bt_sorted["PnL_R"].fillna(0)
    bt_sorted["Cum_R"] = bt_sorted["PnL_R"].cumsum()
    bt_sorted["Date"] = pd.to_datetime(bt_sorted["Date"])

    chart_col_1, chart_col_2 = st.columns(2)
    with chart_col_1:
        outcomes = bt_sorted["Outcome"].value_counts().reindex(["Win", "Loss", "Expired", "Pending"], fill_value=0)
        outcome_fig = go.Figure(
            go.Bar(
                x=outcomes.index,
                y=outcomes.values,
                marker_color=["#00e676", "#ff5252", "#8fb3ff", "#ffca28"],
                text=outcomes.values,
                textposition="outside",
            )
        )
        outcome_fig.update_layout(
            title="Outcome Distribution",
            height=300,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(10,22,45,0.6)",
            font=dict(color="#8899bb"),
            showlegend=False,
            margin=dict(t=40, b=20, l=0, r=0),
        )
        st.plotly_chart(outcome_fig, use_container_width=True)

    with chart_col_2:
        cumulative_fig = go.Figure(
            go.Scatter(
                x=bt_sorted["Date"],
                y=bt_sorted["Cum_R"],
                fill="tozeroy",
                line=dict(color="#00e5ff", width=1.5),
                fillcolor="rgba(0,229,255,0.07)",
            )
        )
        cumulative_fig.update_layout(
            title="Cumulative P&L (R)",
            height=300,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(10,22,45,0.6)",
            font=dict(color="#8899bb"),
            margin=dict(t=40, b=20, l=0, r=0),
        )
        st.plotly_chart(cumulative_fig, use_container_width=True)

    performer_source = bt_sorted[bt_sorted["Outcome"] != "Pending"]
    top_performers = performer_source.groupby("Ticker").agg(
        Trades=("Outcome", "count"),
        Wins=("Outcome", lambda series: (series == "Win").sum()),
        Total_R=("PnL_R", "sum"),
    ).reset_index()
    if not top_performers.empty:
        top_performers["WR%"] = (top_performers["Wins"] / top_performers["Trades"] * 100).round(1)
        top_performers = top_performers.sort_values("Total_R", ascending=False).head(10)

    st.markdown("**Top Performing Tickers**")
    st.dataframe(top_performers, use_container_width=True, hide_index=True)

    csv = bt_df.to_csv(index=False).encode()
    st.download_button("📥 Download Backtest CSV", csv, f"backtest_{datetime.date.today()}.csv", "text/csv")
