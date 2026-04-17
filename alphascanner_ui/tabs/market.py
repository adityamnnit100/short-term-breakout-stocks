"""Market overview tab UI."""

import plotly.graph_objects as go
import streamlit as st


def render_tab(fetch_indices_performance, fetch_fii_dii_data, load_nifty_history, logger) -> None:
    st.markdown('<div class="glass-card"><div class="panel-title" style="color: #00e5ff;">Global Market Snapshot</div></div>', unsafe_allow_html=True)

    with st.spinner("Fetching indices…"):
        index_data = fetch_indices_performance()

    if index_data:
        columns = st.columns(min(len(index_data), 4))
        for index, (name, data) in enumerate(index_data.items()):
            column = columns[index % 4]
            change = data["change"]
            column.metric(name, f"{data['price']:,.2f}", f"{change:+.2f}%", delta_color="normal" if change >= 0 else "inverse")

    st.divider()
    st.markdown('<div class="panel-title" style="color: #ffca28; border-left-color: #ffca28;">Institutional Flow (FII/DII)</div>', unsafe_allow_html=True)

    with st.spinner("Fetching FII/DII data…"):
        fii_dii = fetch_fii_dii_data(logger)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown('<div class="glass-card" style="border-left: 4px solid #00e5ff; height: 100%;">', unsafe_allow_html=True)
        st.caption("FII (Foreign Investors)")
        m1, m2, m3 = st.columns(3)
        m1.metric("Net Flow", f"₹{fii_dii['fii_net']:,.0f} Cr", delta=f"{fii_dii['fii_net']:+,.0f}")
        m2.metric("Gross Buy", f"₹{fii_dii['fii_buy']:,.0f}")
        m3.metric("Gross Sell", f"₹{fii_dii['fii_sell']:,.0f}")
        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="glass-card" style="border-left: 4px solid #ffca28; height: 100%;">', unsafe_allow_html=True)
        st.caption("DII (Domestic Investors)")
        m1, m2, m3 = st.columns(3)
        m1.metric("Net Flow", f"₹{fii_dii['dii_net']:,.0f} Cr", delta=f"{fii_dii['dii_net']:+,.0f}")
        m2.metric("Gross Buy", f"₹{fii_dii['dii_buy']:,.0f}")
        m3.metric("Gross Sell", f"₹{fii_dii['dii_sell']:,.0f}")
        st.markdown('</div>', unsafe_allow_html=True)

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
            line=dict(color="#00e5ff", width=1.8),
            fillcolor="rgba(0,229,255,0.06)",
        )
    )
    figure.update_layout(
        height=320,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(10,22,45,0.6)",
        font=dict(color="#8899bb"),
        margin=dict(t=20, b=20, l=0, r=0),
        showlegend=False,
    )
    figure.update_xaxes(gridcolor="rgba(255,255,255,0.04)")
    figure.update_yaxes(gridcolor="rgba(255,255,255,0.04)")
    st.plotly_chart(figure, use_container_width=True)
