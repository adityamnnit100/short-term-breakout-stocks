"""Reusable table and chart helpers."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots


def render_top_picks(df: pd.DataFrame):
    """
    Fixes the UI issue by rendering Top Picks using unsafe_allow_html.
    Automatically identifies the top 3 high-conviction signals.
    """
    if df is None or df.empty or "Signal_Strength" not in df.columns:
        return

    top_3 = df.nlargest(3, "Signal_Strength")
    
    html = '<div class="top-picks-grid">'
    for _, row in top_3.iterrows():
        symbol = row.get("Ticker", "N/A")
        price = row.get("LTP", 0)
        pattern = row.get("Pattern", "Rounding")
        rsi = row.get("RSI", 0)
        vol = row.get("Vol_x", 0)
        strength = row.get("Signal_Strength", 0)
        
        html += f"""
        <div class="top-pick-card">
            <div class="top-pick-head">
                <div class="top-pick-symbol">{symbol}</div>
                <div class="top-pick-price">₹{price:,.2f}</div>
            </div>
            <div class="top-pick-meta">{pattern}</div>
            <div class="top-pick-tags">
                <span class="mini-tag">RSI {rsi:.1f}</span>
                <span class="mini-tag">Vol {vol:.1f}x</span>
                <span class="mini-tag">Strength {strength:.1f}</span>
            </div>
        </div>
        """
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)


def style_scanner_results(df: pd.DataFrame):
    def _strength(val):
        try:
            value = float(val)
        except Exception:
            return ""
        if value >= 8:
            return "background-color:rgba(16,185,129,0.14);color:#10b981;font-weight:700;"
        if value >= 6:
            return "background-color:rgba(245,158,11,0.12);color:#f59e0b;"
        return "background-color:rgba(244,63,94,0.10);color:#f43f5e;"

    def _rsi(val):
        try:
            value = float(val)
        except Exception:
            return ""
        if value >= 70:
            return "color:#f43f5e;"
        if value <= 40:
            return "color:#10b981;"
        return ""

    def _volume(val):
        try:
            value = float(val)
        except Exception:
            return ""
        if value >= 2:
            return "color:#10b981;font-weight:700;"
        if value >= 1.5:
            return "color:#f59e0b;"
        return "color:#cbd5e1;"

    def _rs(val):
        try:
            value = float(val)
        except Exception:
            return ""
        if value >= 95:
            return "color:#10b981;font-weight:700;"
        if value >= 90:
            return "color:#22d3ee;"
        return "color:#cbd5e1;"

    styled = df.style
    formats = {}
    if "LTP" in df.columns:
        formats["LTP"] = "₹{:.2f}"
    if "RSI" in df.columns:
        formats["RSI"] = "{:.0f}"
    if "RS" in df.columns:
        formats["RS"] = "{:.1f}"
    if "Strength" in df.columns:
        formats["Strength"] = "{:.0f}"
    if "Vol×" in df.columns:
        formats["Vol×"] = "{:.1f}×"
    if formats:
        styled = styled.format(formats)
    if "Strength" in df.columns:
        try:
            styled = styled.map(_strength, subset=["Strength"])
        except AttributeError:
            styled = styled.applymap(_strength, subset=["Strength"])
    if "RSI" in df.columns:
        try:
            styled = styled.map(_rsi, subset=["RSI"])
        except AttributeError:
            styled = styled.applymap(_rsi, subset=["RSI"])
    if "Vol×" in df.columns:
        try:
            styled = styled.map(_volume, subset=["Vol×"])
        except AttributeError:
            styled = styled.applymap(_volume, subset=["Vol×"])
    if "RS" in df.columns:
        try:
            styled = styled.map(_rs, subset=["RS"])
        except AttributeError:
            styled = styled.applymap(_rs, subset=["RS"])
    return styled


def build_chart(
    df: pd.DataFrame,
    ticker: str,
    row_data: dict,
    *,
    show_sma: bool = True,
    show_ema: bool = True,
    show_bb: bool = True,
    show_rsi: bool = True,
    show_macd: bool = True,
    show_vwap: bool = False,
) -> go.Figure:
    row_count = 1 + show_rsi + show_macd
    row_heights = [0.55] + [0.225] * (row_count - 1)
    subplot_titles = [ticker] + (["RSI (14)"] if show_rsi else []) + (["MACD"] if show_macd else [])

    fig = make_subplots(
        rows=row_count,
        cols=1,
        shared_xaxes=True,
        row_heights=row_heights,
        vertical_spacing=0.04,
        subplot_titles=subplot_titles,
    )

    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name="Price",
            increasing_line_color="#10b981",
            decreasing_line_color="#f43f5e",
            increasing_fillcolor="rgba(16, 185, 129, 0.6)",
            decreasing_fillcolor="rgba(244, 63, 94, 0.6)",
        ),
        row=1,
        col=1,
    )

    colors = [
        "rgba(16, 185, 129, 0.35)" if float(close) >= float(open_) else "rgba(244, 63, 94, 0.35)"
        for close, open_ in zip(df["Close"], df["Open"])
    ]
    fig.add_trace(
        go.Bar(
            x=df.index,
            y=df["Volume"],
            name="Volume",
            marker_color=colors,
            showlegend=False,
            yaxis="y2",
        ),
        row=1,
        col=1,
    )

    close = df["Close"]

    if show_sma:
        sma200 = close.rolling(200).mean()
        sma50 = close.rolling(50).mean()
        fig.add_trace(
            go.Scatter(x=df.index, y=sma200, name="SMA 200", line=dict(color="#8b5cf6", width=1.2, dash="dot")),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(x=df.index, y=sma50, name="SMA 50", line=dict(color="#f59e0b", width=1.2, dash="dot")),
            row=1,
            col=1,
        )

    if show_ema:
        ema20 = close.ewm(span=20, adjust=False).mean()
        fig.add_trace(
            go.Scatter(x=df.index, y=ema20, name="EMA 20", line=dict(color="#00ffaa", width=1.4)),
            row=1,
            col=1,
        )

    if show_bb:
        sma = close.rolling(20).mean()
        std = close.rolling(20).std()
        upper, lower = sma + 2 * std, sma - 2 * std
        fig.add_trace(
            go.Scatter(x=df.index, y=upper, name="BB Upper", line=dict(color="rgba(34, 211, 238, 0.5)", width=0.8)),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=lower,
                name="BB Lower",
                fill="tonexty",
                fillcolor="rgba(34, 211, 238, 0.04)",
                line=dict(color="rgba(34, 211, 238, 0.5)", width=0.8),
            ),
            row=1,
            col=1,
        )

    if show_vwap:
        typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
        vwap = (typical_price * df["Volume"]).rolling(20).sum() / df["Volume"].rolling(20).sum()
        fig.add_trace(
            go.Scatter(x=df.index, y=vwap, name="VWAP", line=dict(color="#f59e0b", width=1.2, dash="dashdot")),
            row=1,
            col=1,
        )

    atr = float(row_data.get("ATR", 0))
    ltp = float(row_data.get("LTP", close.iloc[-1]))

    # Add Entry Price Level
    fig.add_hline(
        y=ltp,
        line_color="#22d3ee",
        line_width=1.5,
        line_dash="dot",
        annotation_text=f"<b>ENTRY: ₹{ltp:,.2f}</b>",
        annotation_position="right",
        annotation_font_color="#ffffff",
        annotation_bgcolor="#22d3ee",
        row=1,
        col=1,
    )

    if atr > 0:
        for level, color, label in [
            (ltp - 1.5 * atr, "#f43f5e", "SL"),
            (ltp + 1.0 * atr, "#f59e0b", "TP1"),
            (ltp + 3.0 * atr, "#10b981", "TP2"),
        ]:
            fig.add_hline(
                y=level,
                line_color=color,
                line_width=1,
                line_dash="dash",
                annotation_text=f"<b>{label}: ₹{level:,.2f}</b>",
                annotation_position="right",
                annotation_font_color="#ffffff",
                annotation_bgcolor=color,
                row=1,
                col=1,
            )

    current_row = 2
    if show_rsi:
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - 100 / (1 + gain / loss.replace(0, float("nan")))
        fig.add_trace(
            go.Scatter(x=df.index, y=rsi, name="RSI", line=dict(color="#22d3ee", width=1.4)),
            row=current_row,
            col=1,
        )
        fig.add_hline(y=70, line_color="rgba(244, 63, 94, 0.4)", line_dash="dot", row=current_row, col=1)
        fig.add_hline(y=30, line_color="rgba(16, 185, 129, 0.4)", line_dash="dot", row=current_row, col=1)
        current_row += 1

    if show_macd:
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        histogram = macd - signal
        bar_colors = ["rgba(16, 185, 129, 0.6)" if value >= 0 else "rgba(244, 63, 94, 0.6)" for value in histogram]
        fig.add_trace(
            go.Bar(x=df.index, y=histogram, name="Histogram", marker_color=bar_colors, showlegend=False),
            row=current_row,
            col=1,
        )
        fig.add_trace(
            go.Scatter(x=df.index, y=macd, name="MACD", line=dict(color="#22d3ee", width=1.2)),
            row=current_row,
            col=1,
        )
        fig.add_trace(
            go.Scatter(x=df.index, y=signal, name="Signal", line=dict(color="#f59e0b", width=1.2)),
            row=current_row,
            col=1,
        )

    fig.update_layout(
        height=720,
        paper_bgcolor="rgba(5,13,26,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="JetBrains Mono", color="#8899bb", size=11),
        xaxis_rangeslider_visible=False,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.01,
            xanchor="right",
            x=1,
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=10),
        ),
        margin=dict(l=0, r=100, t=40, b=0),
        yaxis2=dict(
            overlaying="y",
            side="right",
            showgrid=False,
            showticklabels=False,
            range=[0, df["Volume"].max() * 6],
        ),
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.04)", zeroline=False)
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.04)", zeroline=False)
    return fig
