"""Reusable table and chart helpers."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots


CHART_BG = "#ffffff"
PLOT_BG = "#ffffff"
GRID = "rgba(15, 23, 42, 0.08)"
TEXT = "#334155"
MUTED = "#64748b"
UP = "#16a34a"
DOWN = "#dc2626"
CYAN = "#0284c7"
AMBER = "#d97706"
PURPLE = "#7c3aed"


def apply_trading_layout(fig: go.Figure, *, height: int, title: str = "", show_legend: bool = True) -> go.Figure:
    """Apply a TradingView/Zerodha-inspired chart shell to Plotly figures."""
    fig.update_layout(
        title=dict(text=title, x=0.01, xanchor="left", font=dict(size=14, color="#0f172a")),
        height=height,
        paper_bgcolor=CHART_BG,
        plot_bgcolor=PLOT_BG,
        font=dict(family="JetBrains Mono, monospace", color=TEXT, size=11),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor="#0f172a",
            bordercolor="#334155",
            font=dict(color="#f8fafc", family="JetBrains Mono, monospace", size=11),
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.01,
            xanchor="right",
            x=1,
            bgcolor="rgba(255,255,255,0.88)",
            bordercolor="rgba(15,23,42,0.10)",
            borderwidth=1,
            font=dict(size=10, color=TEXT),
        ),
        margin=dict(l=8, r=64, t=42 if title else 30, b=26),
        showlegend=show_legend,
        dragmode="pan",
        modebar=dict(
            orientation="v",
            bgcolor="rgba(255,255,255,0.85)",
            color=MUTED,
            activecolor=CYAN,
        ),
    )
    fig.update_xaxes(
        showgrid=True,
        gridcolor=GRID,
        zeroline=False,
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikecolor="rgba(15,23,42,0.35)",
        spikethickness=1,
        rangeslider_visible=False,
        rangebreaks=[dict(bounds=["sat", "mon"])],
        linecolor="rgba(15,23,42,0.16)",
        tickfont=dict(color=MUTED),
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor=GRID,
        zeroline=False,
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikecolor="rgba(15,23,42,0.35)",
        spikethickness=1,
        side="right",
        linecolor="rgba(15,23,42,0.16)",
        tickfont=dict(color=MUTED),
    )
    return fig


def render_top_picks(df: pd.DataFrame):
    """
    Fixes the UI issue by rendering Top Picks using unsafe_allow_html.
    Automatically identifies the top 3 high-conviction signals.
    """
    if df is None or df.empty or "Signal_Strength" not in df.columns:
        return

    st.markdown("### ⭐ Top Breakout Picks")
    top_3 = df.nlargest(3, "Signal_Strength")
    
    html = '<div class="top-picks-grid">'
    for _, row in top_3.iterrows():
        symbol = row.get("Ticker", "N/A")
        price = row.get("LTP", 0)
        pattern = row.get("Pattern", "Rounding")
        rsi = row.get("RSI", 0)
        vol = row.get("Vol_x", 0)
        strength = row.get("Signal_Strength", 0)
        
        html += (
            f'<div class="top-pick-card">'
            f'<div class="top-pick-head"><div class="top-pick-symbol">{symbol}</div>'
            f'<div class="top-pick-price">₹{price:,.2f}</div></div>'
            f'<div class="top-pick-meta">{pattern}</div>'
            f'<div class="top-pick-tags">'
            f'<span class="mini-tag">RSI {rsi:.1f}</span>'
            f'<span class="mini-tag">Vol {vol:.1f}x</span>'
            f'<span class="mini-tag">Strength {strength:.1f}</span>'
            f'</div></div>'
        )
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

    def _action(val):
        v = str(val)
        if "VCP" in v:
            return "color:#8b5cf6; font-weight:700;" # Purple for VCP
        if "Ready" in v:
            return "color:#00ffaa; font-weight:700;" # Neon Green for Breakout
        return ""

    def _setup(val):
        try:
            value = float(val)
        except Exception:
            return ""
        if value >= 8:
            return "color:#8b5cf6; font-weight:700;" # Vivid Purple for elite setup
        if value >= 5:
            return "color:#a78bfa;" # Lighter Purple
        return ""

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
    if "Stop%" in df.columns:
        formats["Stop%"] = "{:.1f}%"
    if "RR" in df.columns:
        formats["RR"] = "{:.1f}"
    if "Setup" in df.columns:
        formats["Setup"] = "{:.1f}"
    if "Tight Days" in df.columns:
        formats["Tight Days"] = "{:.0f}d"
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
    if "Action" in df.columns:
        try:
            styled = styled.map(_action, subset=["Action"])
        except AttributeError:
            styled = styled.applymap(_action, subset=["Action"])
    if "Setup" in df.columns:
        try:
            styled = styled.map(_setup, subset=["Setup"])
        except AttributeError:
            styled = styled.applymap(_setup, subset=["Setup"])
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
    row_count = 2 + show_rsi + show_macd
    row_heights = [0.60, 0.14] + [0.13] * (row_count - 2)
    subplot_titles = [ticker, "Volume"] + (["RSI (14)"] if show_rsi else []) + (["MACD"] if show_macd else [])

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
            increasing_line_color=UP,
            decreasing_line_color=DOWN,
            increasing_fillcolor="rgba(22, 163, 74, 0.72)",
            decreasing_fillcolor="rgba(220, 38, 38, 0.72)",
            whiskerwidth=0.35,
            hovertemplate=(
                "<b>%{x|%d %b %Y}</b><br>"
                "Open %{open:.2f}<br>"
                "High %{high:.2f}<br>"
                "Low %{low:.2f}<br>"
                "Close %{close:.2f}<extra></extra>"
            ),
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
            opacity=0.72,
            showlegend=False,
            hovertemplate="Volume %{y:,.0f}<extra></extra>",
        ),
        row=2,
        col=1,
    )

    close = df["Close"]

    if show_sma:
        sma200 = close.rolling(200).mean()
        sma50 = close.rolling(50).mean()
        fig.add_trace(
            go.Scatter(x=df.index, y=sma200, name="SMA 200", line=dict(color=PURPLE, width=1.2), hovertemplate="SMA 200 %{y:.2f}<extra></extra>"),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(x=df.index, y=sma50, name="SMA 50", line=dict(color=AMBER, width=1.2), hovertemplate="SMA 50 %{y:.2f}<extra></extra>"),
            row=1,
            col=1,
        )

    if show_ema:
        ema20 = close.ewm(span=20, adjust=False).mean()
        fig.add_trace(
            go.Scatter(x=df.index, y=ema20, name="EMA 20", line=dict(color=CYAN, width=1.5), hovertemplate="EMA 20 %{y:.2f}<extra></extra>"),
            row=1,
            col=1,
        )

    if show_bb:
        sma = close.rolling(20).mean()
        std = close.rolling(20).std()
        upper, lower = sma + 2 * std, sma - 2 * std
        fig.add_trace(
            go.Scatter(x=df.index, y=upper, name="BB Upper", line=dict(color="rgba(2, 132, 199, 0.38)", width=0.9), hovertemplate="BB Upper %{y:.2f}<extra></extra>"),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=lower,
                name="BB Lower",
                fill="tonexty",
                fillcolor="rgba(2, 132, 199, 0.045)",
                line=dict(color="rgba(2, 132, 199, 0.38)", width=0.9),
                hovertemplate="BB Lower %{y:.2f}<extra></extra>",
            ),
            row=1,
            col=1,
        )

    if show_vwap:
        typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
        vwap = (typical_price * df["Volume"]).rolling(20).sum() / df["Volume"].rolling(20).sum()
        fig.add_trace(
            go.Scatter(x=df.index, y=vwap, name="VWAP", line=dict(color="#9333ea", width=1.2, dash="dash"), hovertemplate="VWAP %{y:.2f}<extra></extra>"),
            row=1,
            col=1,
        )

    atr = float(row_data.get("ATR", 0))
    ltp = float(row_data.get("LTP", close.iloc[-1]))

    resistance = row_data.get("_Resistance")
    support1 = row_data.get("_Support1")
    support2 = row_data.get("_Support2")

    fig.add_hline(
        y=ltp,
        line_color=CYAN,
        line_width=1.4,
        line_dash="dot",
        annotation_text=f"ENTRY {ltp:,.2f}",
        annotation_position="right",
        annotation_font_color="#ffffff",
        annotation_bgcolor=CYAN,
        row=1,
        col=1,
    )

    if atr > 0:
        for level, color, label in [
            (ltp - 1.5 * atr, DOWN, "SL"),
            (ltp + 1.0 * atr, AMBER, "TP1"),
            (ltp + 3.0 * atr, UP, "TP2"),
        ]:
            fig.add_hline(
                y=level,
                line_color=color,
                line_width=1,
                line_dash="dash",
                annotation_text=f"{label} {level:,.2f}",
                annotation_position="right",
                annotation_font_color="#ffffff",
                annotation_bgcolor=color,
                row=1,
                col=1,
            )

    for value, color, label in [
        (resistance, "#0f766e", "RES"),
        (support1, "#475569", "S1"),
        (support2, "#64748b", "S2"),
    ]:
        try:
            level = float(value)
        except (TypeError, ValueError):
            continue
        if level > 0:
            fig.add_hline(
                y=level,
                line_color=color,
                line_width=0.9,
                line_dash="dot",
                annotation_text=f"{label} {level:,.2f}",
                annotation_position="right",
                annotation_font_color="#ffffff",
                annotation_bgcolor=color,
                row=1,
                col=1,
            )

    current_row = 3
    if show_rsi:
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - 100 / (1 + gain / loss.replace(0, float("nan")))
        fig.add_trace(
            go.Scatter(x=df.index, y=rsi, name="RSI", line=dict(color=CYAN, width=1.4), hovertemplate="RSI %{y:.1f}<extra></extra>"),
            row=current_row,
            col=1,
        )
        fig.add_hrect(y0=70, y1=100, fillcolor="rgba(220, 38, 38, 0.06)", line_width=0, row=current_row, col=1)
        fig.add_hrect(y0=0, y1=30, fillcolor="rgba(22, 163, 74, 0.06)", line_width=0, row=current_row, col=1)
        fig.add_hline(y=70, line_color="rgba(220, 38, 38, 0.45)", line_dash="dot", row=current_row, col=1)
        fig.add_hline(y=50, line_color="rgba(100, 116, 139, 0.35)", line_dash="dot", row=current_row, col=1)
        fig.add_hline(y=30, line_color="rgba(22, 163, 74, 0.45)", line_dash="dot", row=current_row, col=1)
        fig.update_yaxes(range=[0, 100], row=current_row, col=1)
        current_row += 1

    if show_macd:
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        histogram = macd - signal
        bar_colors = ["rgba(22, 163, 74, 0.68)" if value >= 0 else "rgba(220, 38, 38, 0.68)" for value in histogram]
        fig.add_trace(
            go.Bar(x=df.index, y=histogram, name="Histogram", marker_color=bar_colors, showlegend=False, hovertemplate="Hist %{y:.2f}<extra></extra>"),
            row=current_row,
            col=1,
        )
        fig.add_trace(
            go.Scatter(x=df.index, y=macd, name="MACD", line=dict(color=CYAN, width=1.2), hovertemplate="MACD %{y:.2f}<extra></extra>"),
            row=current_row,
            col=1,
        )
        fig.add_trace(
            go.Scatter(x=df.index, y=signal, name="Signal", line=dict(color=AMBER, width=1.2), hovertemplate="Signal %{y:.2f}<extra></extra>"),
            row=current_row,
            col=1,
        )

    apply_trading_layout(fig, height=760, title=f"{ticker} · Price Action")
    fig.update_yaxes(title_text="Price", row=1, col=1)
    fig.update_yaxes(title_text="Vol", row=2, col=1, showgrid=False)
    return fig
