"""Reusable table and chart helpers."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
from typing import Optional


CHART_BG = "#051725"
PLOT_BG = "#03121a"
GRID = "rgba(255,255,255,0.035)"
TEXT = "#d7e9f5"
MUTED = "#92a9bf"
UP = "#07b285"  # rising candle border (hollow)
DOWN = "#ff3b30"  # falling candle fill
CYAN = "#22d3ee"
AMBER = "#ffb430"
PURPLE = "#8b5cf6"


def apply_trading_layout(
    fig: go.Figure, *, height: int, title: str = "", subtitle: Optional[str] = None, show_legend: bool = True, theme: str = "dark"
) -> go.Figure:
    """Apply a TradingView/Zerodha-inspired chart shell to Plotly figures.

    theme: 'dark' or 'light' — controls background and color choices.
    """
    dark = theme == "dark"
    paper_bg = CHART_BG if dark else "#ffffff"
    plot_bg = PLOT_BG if dark else "#ffffff"
    text_color = TEXT if dark else "#0f172a"

    # Combine title and subtitle into a single HTML title to avoid layout overlap
    title_text = title
    if subtitle:
        # use muted color for subtitle
        title_text = f"{title}<br><span style=\"font-size:11px;color:{MUTED};\">{subtitle}</span>"

    fig.update_layout(
        title=dict(text=title_text, x=0.01, xanchor="left", font=dict(size=13, color=text_color), ),
        height=height,
        paper_bgcolor=paper_bg,
        plot_bgcolor=plot_bg,
        font=dict(family="Inter, Arial, sans-serif", color=text_color, size=12),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor=("rgba(6,20,37,0.96)" if dark else "#ffffff"),
            bordercolor=("rgba(255,255,255,0.06)" if dark else "rgba(15,23,42,0.06)"),
            font=dict(color=("#d7e9f5" if dark else "#0f172a"), family="Inter, Arial, sans-serif", size=11),
            align="left",
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.01,
            xanchor="right",
            x=1,
            bgcolor=("rgba(4,8,12,0.16)" if dark else "rgba(255,255,255,0.88)"),
            bordercolor=("rgba(255,255,255,0.03)" if dark else "rgba(15,23,42,0.10)"),
            borderwidth=1,
            font=dict(size=10, color=text_color),
        ),
        # Leave room for the title, legend and the single range selector.
        margin=dict(l=8, r=64, t=96 if title else 42, b=34),
        showlegend=show_legend,
        dragmode="pan",
        modebar=dict(
            orientation="v",
            bgcolor=("rgba(0,0,0,0.12)" if dark else "rgba(255,255,255,0.85)"),
            color=MUTED,
            activecolor=CYAN,
            remove=["zoomIn2d", "zoomOut2d", "select2d"],
        ),
    )
    fig.update_xaxes(
        showgrid=False if dark else True,
        gridcolor=GRID,
        zeroline=False,
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikecolor=("rgba(255,255,255,0.14)" if dark else "rgba(15,23,42,0.12)"),
        spikethickness=1.2,
        # Subplots share their x range, but each still owns an x-axis object. Keep
        # navigation off those axes here; it is added once below.
        rangeslider_visible=False,
        rangeselector_visible=False,
        linecolor=("rgba(255,255,255,0.03)" if dark else "rgba(15,23,42,0.16)"),
        tickfont=dict(color=MUTED, size=11),
    )
    datetime_indexes = []
    for trace in fig.data:
        trace_x = getattr(trace, "x", None)
        if trace_x is None:
            continue
        trace_index = pd.Index(trace_x)
        if pd.api.types.is_datetime64_any_dtype(trace_index.dtype):
            datetime_indexes.append(pd.DatetimeIndex(trace_index))

    has_time_axis = bool(datetime_indexes) or any(trace.type == "candlestick" for trace in fig.data)
    uses_daily_points = any(
        len(index) > 1
        and index.to_series().diff().dropna().median() >= pd.Timedelta(days=1)
        for index in datetime_indexes
    )
    one_day_count = 5 if uses_daily_points else 1

    range_selector = dict(
        visible=True,
        x=0.99,
        xanchor="right",
        y=1.14,
        yanchor="bottom",
        bgcolor=("#0b2535" if dark else "#f1f5f9"),
        activecolor=("#0e7490" if dark else "#bae6fd"),
        bordercolor=("#24475b" if dark else "#cbd5e1"),
        font=dict(size=11, color=("#f8fafc" if dark else "#0f172a")),
        buttons=[
            # A one-day viewport can contain only one daily point, for which a
            # candlestick has no useful width. Keep the requested 1D option but
            # retain enough daily observations to render visible candles.
            dict(count=one_day_count, label="1D", step="day", stepmode="backward"),
            dict(count=1, label="1M", step="month", stepmode="backward"),
            dict(count=1, label="YTD", step="year", stepmode="todate"),
            dict(count=1, label="1Y", step="year", stepmode="backward"),
            dict(step="all", label="All"),
        ],
    )
    # Address axes by layout name rather than row/column. This helper is also
    # used by ordinary go.Figure charts, which do not have a subplot grid.
    xaxis_names = sorted(
        (name for name in fig.layout if name.startswith("xaxis")),
        key=lambda name: int(name[5:] or 1),
    )
    if has_time_axis:
        for xaxis_name in xaxis_names or ["xaxis"]:
            fig.layout[xaxis_name].type = "date"
        # Attach the selector to the first time-series axis. In the price chart
        # this is the axis that owns the candlestick trace; putting short ranges
        # on an indicator axis can leave the matched candle layer unpainted.
        candle_xaxis = xaxis_names[0] if xaxis_names else "xaxis"
        fig.layout[candle_xaxis].rangeselector = range_selector
    fig.update_yaxes(
        showgrid=False if dark else True,
        gridcolor=GRID,
        zeroline=False,
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikecolor=("rgba(255,255,255,0.14)" if dark else "rgba(15,23,42,0.12)"),
        spikethickness=1.2,
        side="right",
        linecolor=("rgba(255,255,255,0.03)" if dark else "rgba(15,23,42,0.16)"),
        tickfont=dict(color=MUTED, size=11),
    )
    # subtitle is embedded in the title HTML to avoid overlap with plot elements
    return fig


def plotly_config(theme: str = "dark") -> dict:
    """Return a Plotly `config` dict suitable for Streamlit's `st.plotly_chart`.

    Usage: `st.plotly_chart(fig, config=plotly_config())`
    """
    remove = ["zoomIn2d", "zoomOut2d", "select2d", "lasso2d", "toggleSpikelines"]
    conf = {
        "modeBarButtonsToRemove": remove,
        "displaylogo": False,
        "scrollZoom": True,
        "toImageButtonOptions": {"format": "png", "filename": "chart", "height": 800, "width": 1400, "scale": 1},
    }
    return conf


def render_top_picks(df: pd.DataFrame):
    """
    Fixes the UI issue by rendering Top Picks using unsafe_allow_html.
    Automatically identifies the top 3 high-conviction signals.
    """
    if df is None or df.empty:
        return

    st.markdown("### ⭐ Top Breakout Picks")
    if "Signal_Strength" in df.columns:
        score_col = "Signal_Strength"
        score_label = "Signal Strength"
    elif "Watchlist Score" in df.columns:
        score_col = "Watchlist Score"
        score_label = "Watchlist Score"
    elif "Entry Score" in df.columns:
        score_col = "Entry Score"
        score_label = "Entry Score"
    else:
        return

    top_3 = df.nlargest(3, score_col)
    
    html = '<div class="top-picks-grid">'
    for _, row in top_3.iterrows():
        symbol = row.get("Ticker", "N/A")
        price = row.get("LTP", 0)
        pattern = row.get("Pattern", "Rounding")
        rsi = row.get("RSI", 0)
        vol = row.get("Vol_x", 0)
        strength = row.get(score_col, 0)
        risk = row.get("Risk_Grade", "C")
        breadth = row.get("Market_Health", "Unknown")
        stop_pct = row.get("Stop_%", 0)
        
        html += (
            f'<div class="top-pick-card">'
            f'<div class="top-pick-head"><div class="top-pick-symbol">{symbol}</div>'
            f'<div class="top-pick-price">₹{price:,.2f}</div></div>'
            f'<div class="top-pick-meta">{pattern}</div>'
            f'<div class="top-pick-tags">'
            f'<span class="mini-tag">RSI {rsi:.1f}</span>'
            f'<span class="mini-tag">Vol {vol:.1f}x</span>'
            f'<span class="mini-tag">{score_label} {strength:.1f}</span>'
            f'<span class="mini-tag">Risk {risk}</span>'
            f'<span class="mini-tag">Breadth {breadth}</span>'
            f'<span class="mini-tag">Stop {stop_pct:.1f}%</span>'
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

    def _risk(val):
        value = str(val)
        if value == "A":
            return "background-color:rgba(22,163,74,0.14);color:#15803d;font-weight:700;"
        if value == "B":
            return "background-color:rgba(2,132,199,0.12);color:#0369a1;font-weight:700;"
        if value == "Reduce/Skip":
            return "background-color:rgba(220,38,38,0.12);color:#b91c1c;font-weight:700;"
        return "background-color:rgba(217,119,6,0.10);color:#92400e;"

    def _breadth(val):
        value = str(val)
        if value in {"Risk-On", "Constructive"}:
            return "color:#15803d;font-weight:700;"
        if value == "Risk-Off":
            return "color:#b91c1c;font-weight:700;"
        return "color:#92400e;"

    def _execution(val):
        value = str(val)
        if value == "Ready":
            return "background-color:rgba(16,185,129,0.16);color:#166534;font-weight:700;"
        if value == "Caution":
            return "background-color:rgba(245,158,11,0.12);color:#92400e;font-weight:700;"
        if value == "Watch":
            return "background-color:rgba(59,130,246,0.12);color:#1d4ed8;font-weight:700;"
        return "background-color:rgba(220,38,38,0.12);color:#991b1b;font-weight:700;"

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
    for column in ["FII+", "FII%", "ROCE", "Profit%", "Sales%"]:
        if column in df.columns:
            formats[column] = "{:.1f}%"
    if "PE" in df.columns:
        formats["PE"] = "{:.1f}"
    if "MktCap" in df.columns:
        formats["MktCap"] = "₹{:.0f}Cr"
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
    if "Risk" in df.columns:
        try:
            styled = styled.map(_risk, subset=["Risk"])
        except AttributeError:
            styled = styled.applymap(_risk, subset=["Risk"])
    if "Breadth" in df.columns:
        try:
            styled = styled.map(_breadth, subset=["Breadth"])
        except AttributeError:
            styled = styled.applymap(_breadth, subset=["Breadth"])
    if "Execution" in df.columns:
        try:
            styled = styled.map(_execution, subset=["Execution"])
        except AttributeError:
            styled = styled.applymap(_execution, subset=["Execution"])
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
    theme: str = "dark",
) -> go.Figure:
    row_count = 2 + show_rsi + show_macd
    row_heights = [0.60, 0.14] + [0.13] * (row_count - 2)
    subplot_titles = ["Price", "Volume"] + (["RSI (14)"] if show_rsi else []) + (["MACD"] if show_macd else [])
    # Rows: Price, Volume, PVT, (optional) RSI, (optional) MACD
    row_count = 3 + (1 if show_rsi else 0) + (1 if show_macd else 0)
    # Give most space to price, then compact rows for indicators
    row_heights = [0.56, 0.12, 0.10] + [0.11] * (row_count - 3)
    subplot_titles = ["Price", "Volume", "PVT"] + (["RSI (14)"] if show_rsi else []) + (["MACD"] if show_macd else [])

    # Defensive: ensure datetime index and sorted order for Plotly candlesticks
    if df is None or df.empty:
        # return an empty figure with title to avoid crashes upstream
        fig = go.Figure()
        # infer timeframe label not possible for empty df
        return apply_trading_layout(fig, height=480, title=ticker, subtitle=None, theme=theme)

    if not isinstance(df.index, pd.DatetimeIndex):
        try:
            df.index = pd.to_datetime(df.index)
        except Exception:
            pass
    df = df.sort_index()

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
            increasing_fillcolor="rgba(7, 178, 133, 0.72)",
            decreasing_fillcolor="rgba(220, 38, 38, 0.85)",
            increasing_line_width=1.1,
            decreasing_line_width=1.1,
            whiskerwidth=0.25,
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

    # Small buy/sell markers per candle (compact markers to reduce clutter)
    try:
        bs_colors = [UP if c >= o else DOWN for c, o in zip(df['Close'], df['Open'])]
        bs_symbols = ['triangle-up' if c >= o else 'triangle-down' for c, o in zip(df['Close'], df['Open'])]
        # place markers slightly above the high for sells and slightly below the low for buys
        marker_y = [h * 1.002 if c < o else l * 0.998 for c, o, h, l in zip(df['Close'], df['Open'], df['High'], df['Low'])]
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=marker_y,
                mode='markers',
                marker=dict(color=bs_colors, size=6, symbol=bs_symbols, opacity=0.65),
                hoverinfo='skip',
                showlegend=False,
            ),
            row=1,
            col=1,
        )
    except Exception:
        pass

    colors = [
        UP if float(close) >= float(open_) else DOWN
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
            go.Scatter(x=df.index, y=ema20, name="EMA 20", line=dict(color=CYAN, width=1.1), hovertemplate="EMA 20 %{y:.2f}<extra></extra>"),
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
    # PVT: Price-Volume Trend (cumulative)
    try:
        prev_close = df["Close"].shift(1)
        pct_change = (df["Close"] - prev_close) / prev_close.replace(0, float("nan"))
        pvt = (pct_change.fillna(0) * df["Volume"]).cumsum()
        fig.add_trace(
            go.Scatter(x=df.index, y=pvt, name="PVT", line=dict(color=CYAN, width=1.2), hovertemplate="PVT %{y:.2f}<extra></extra>"),
            row=3,
            col=1,
        )
    except Exception:
        pvt = None
    current_row += 1
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

    # The timeframe already exists in the chart controls; repeating it beneath
    # the title wastes header space and makes it look like a second selector.
    fig = apply_trading_layout(fig, height=760, title=f"{ticker} · Price Action", theme=theme)
    # Scanner charts use an explicit Streamlit range control. Hide Plotly's
    # client-side selector, which is unreliable with matched subplot axes.
    fig.update_xaxes(rangeselector_visible=False, rangeslider_visible=False)
    fig.update_yaxes(title_text="Price", row=1, col=1)
    fig.update_yaxes(title_text="Vol", row=2, col=1, showgrid=False)
    # Compact header: show ticker and last-traded price as a small badge (paper coords)
    try:
        last_close = float(df['Close'].iloc[-1])
        prev_close = float(df['Close'].iloc[-2]) if len(df) > 1 else last_close
        pct = (last_close - prev_close) / max(prev_close, 1e-9) * 100
        ltp_text = f"{ticker} · ₹{last_close:,.2f} · {pct:+.2f}%"
        ltp_color = CYAN if pct >= 0 else DOWN
        fig.add_annotation(xref='paper', yref='paper', x=0.005, y=1.015, align='left', showarrow=False,
                           text=ltp_text, font=dict(size=11, color=ltp_color, family='Inter'),
                           bgcolor=('rgba(0,0,0,0.0)' if theme=='dark' else '#ffffffcc'), borderpad=6)
    except Exception:
        pass

    # BUY/SELL badge near latest candle (heuristic: green if last close>open else red)
    try:
        last_open = float(df['Open'].iloc[-1])
        last_close = float(df['Close'].iloc[-1])
        tag = 'BUY' if last_close >= last_open else 'SELL'
        tag_color = UP if tag == 'BUY' else DOWN
        # place compact badge slightly above the last candle
        x_pos = df.index[-1]
        y_pos = df['High'].iloc[-1] * 1.006
        fig.add_annotation(x=x_pos, y=y_pos, text=tag, showarrow=False, font=dict(color='#000000', size=9, family='Inter'),
                           align='center', bgcolor=tag_color, borderpad=3, opacity=0.98)
    except Exception:
        pass
    return fig
