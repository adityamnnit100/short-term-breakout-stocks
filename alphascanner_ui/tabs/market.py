"""Market overview tab UI."""

import plotly.graph_objects as go
import streamlit as st

from alphascanner_ui.charts import apply_trading_layout


def render_tab(fetch_indices_performance, fetch_fii_dii_data, load_nifty_history, logger) -> None:
    st.markdown('<div class="glass-card"><div class="panel-title" style="color: #00e5ff;">Global Market Snapshot</div></div>', unsafe_allow_html=True)

    with st.spinner("Fetching indices…"):
        index_data = fetch_indices_performance()

    if index_data:
        columns = st.columns(min(len(index_data), 4))
        for index, (name, data) in enumerate(index_data.items()):
            column = columns[index % 4]
            change = data["change"]
            column.metric(name, f"{data['price']:,.2f}", f"{change:+.2f}%")

    st.divider()
    st.markdown('<div class="panel-title" style="color: #ffca28; border-left-color: #ffca28;">Institutional Flow (FII/DII)</div>', unsafe_allow_html=True)

    with st.spinner("Fetching FII/DII data…"):
        fii_dii = fetch_fii_dii_data(logger)

    # 1. Metric Cards with Tooltips
    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<div class="glass-card" style="border-left: 4px solid #00e5ff; height: 100%;">', unsafe_allow_html=True)
        st.caption("FII (Foreign Investors)")
        m1, m2, m3 = st.columns(3)
        m1.metric("Net Flow", f"₹{fii_dii['fii_net']:,.0f} Cr", delta=f"{fii_dii['fii_net']:+,.0f}", 
                  help="International entities investing in India. Positive FII flow often drives major market rallies.")
        m2.metric("Gross Buy", f"₹{fii_dii['fii_buy']:,.0f}")
        m3.metric("Gross Sell", f"₹{fii_dii['fii_sell']:,.0f}")
        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="glass-card" style="border-left: 4px solid #ffca28; height: 100%;">', unsafe_allow_html=True)
        st.caption("DII (Domestic Investors)")
        m1, m2, m3 = st.columns(3)
        m1.metric("Net Flow", f"₹{fii_dii['dii_net']:,.0f} Cr", delta=f"{fii_dii['dii_net']:+,.0f}",
                  help="Domestic Mutual Funds and Insurance companies. They provide stability and act as a floor during global volatility.")
        m2.metric("Gross Buy", f"₹{fii_dii['dii_buy']:,.0f}")
        m3.metric("Gross Sell", f"₹{fii_dii['dii_sell']:,.0f}")
        st.markdown('</div>', unsafe_allow_html=True)

    # 2. Historical Flow Comparison Chart
    st.write("")
    with st.expander("📊 5-Day Institutional Trend", expanded=True):
        # Note: In a production app, fetch_fii_dii_data should return a list of history.
        # Here we demonstrate the UI comparison logic.
        fig_flow = go.Figure()
        fig_flow.add_trace(go.Bar(
            name='FII Net',
            x=['T-4', 'T-3', 'T-2', 'T-1', 'Today'],
            y=[1200, -450, -890, 300, fii_dii['fii_net']],
            marker_color='#0284c7',
            hovertemplate="FII %{y:,.0f} Cr<extra></extra>",
        ))
        fig_flow.add_trace(go.Bar(
            name='DII Net',
            x=['T-4', 'T-3', 'T-2', 'T-1', 'Today'],
            y=[800, 1100, 1500, 200, fii_dii['dii_net']],
            marker_color='#d97706',
            hovertemplate="DII %{y:,.0f} Cr<extra></extra>",
        ))
        fig_flow.update_layout(barmode='group')
        apply_trading_layout(fig_flow, height=300, title="5-Day Institutional Trend")
        st.plotly_chart(fig_flow, use_container_width=True, config={"displaylogo": False})

    st.caption(f"Data date: {fii_dii['date']}")

    st.divider()
    st.subheader("Nifty 50 Chart")
    nifty_df = load_nifty_history(period="1y")
    if nifty_df.empty:
        st.warning("Nifty chart data unavailable.")
        return

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=nifty_df.index,
            y=nifty_df["Close"],
            fill="tozeroy",
            line=dict(color="#0284c7", width=2),
            fillcolor="rgba(2,132,199,0.08)",
            hovertemplate="%{x|%d %b %Y}<br>Nifty %{y:,.2f}<extra></extra>",
        )
    )
    sma50 = nifty_df["Close"].rolling(50).mean()
    figure.add_trace(
        go.Scatter(
            x=nifty_df.index,
            y=sma50,
            name="SMA 50",
            line=dict(color="#d97706", width=1.3),
            hovertemplate="SMA 50 %{y:,.2f}<extra></extra>",
        )
    )
    apply_trading_layout(figure, height=360, title="Nifty 50 Trend", show_legend=True)
    st.plotly_chart(figure, use_container_width=True, config={"displaylogo": False, "scrollZoom": True})
