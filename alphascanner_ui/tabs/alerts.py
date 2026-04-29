"""Trading alerts and notifications configuration tab."""

import pandas as pd
import streamlit as st

from breakout import calculate_atr
from alphascanner_ui.services.alerts_service import get_alerts_service


def _update_trailing_stop_positions(load_ticker_history) -> None:
    if load_ticker_history is None or not st.session_state.get("trailing_stops_enabled"):
        return

    positions = st.session_state.get("trailing_stop_positions", [])
    if not positions:
        return

    service = None
    has_telegram = st.session_state.get("telegram_token") and st.session_state.get("telegram_chat_id")
    has_whatsapp = st.session_state.get("whatsapp_webhook_url")
    if (
        st.session_state.get("alerts_enabled")
        and st.session_state.get("alert_stop_hit", True)
        and (has_telegram or has_whatsapp)
    ):
        service = get_alerts_service(
            st.session_state.get("telegram_token"),
            st.session_state.get("telegram_chat_id"),
            st.session_state.get("whatsapp_webhook_url"),
        )

    updated_positions = []
    for position in positions:
        ticker = position.get("ticker")
        if not ticker:
            continue
        history = load_ticker_history(ticker, period="3mo", interval="1d")
        if history.empty or len(history) < 20:
            updated_positions.append(position)
            continue

        current_price = float(history["Close"].iloc[-1])
        atr = float(calculate_atr(history["High"], history["Low"], history["Close"]).iloc[-1])
        if pd.isna(atr) or atr <= 0:
            atr = current_price * 0.015

        entry_price = float(position.get("entry_price", current_price) or current_price)
        quantity = int(position.get("quantity", 0) or 0)
        atr_multiplier = float(st.session_state.get("trailing_stop_atr_multiplier", position.get("atr_multiplier", 1.5)) or 1.5)
        highest_price = max(float(position.get("highest_price", entry_price) or entry_price), current_price)
        previous_stop = float(position.get("trailing_stop", entry_price) or entry_price)
        trailing_stop = max(previous_stop, highest_price - (atr * atr_multiplier))
        status = "STOPPED_OUT" if current_price <= trailing_stop else "ACTIVE"

        position.update(
            {
                "current_price": current_price,
                "highest_price": highest_price,
                "trailing_stop": trailing_stop,
                "atr": atr,
                "atr_multiplier": atr_multiplier,
                "pnl": (current_price - entry_price) * quantity,
                "pnl_pct": ((current_price - entry_price) / entry_price * 100) if entry_price > 0 else 0.0,
                "distance_to_stop": current_price - trailing_stop,
                "status": status,
            }
        )

        if status == "STOPPED_OUT" and service and not position.get("alert_sent"):
            sent = service.send_position_alert(
                ticker,
                "TRAILING_STOP",
                current_price,
                trailing_stop,
                "Trailing stop was hit.",
            )
            position["alert_sent"] = bool(sent)

        updated_positions.append(position)

    st.session_state.trailing_stop_positions = updated_positions


def render_tab(load_ticker_history=None) -> None:
    """Render the alerts and notifications configuration tab."""
    _update_trailing_stop_positions(load_ticker_history)
    
    st.markdown('<div class="glass-card"><div class="panel-title" style="color: #00e5ff;">Trading Alerts & Notifications</div></div>', unsafe_allow_html=True)
    
    # Alerts Overview
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Alerts Enabled", "✓ ON" if st.session_state.get("alerts_enabled") else "✗ OFF")
    with col2:
        st.metric("Telegram Connected", "✓ YES" if st.session_state.get("telegram_chat_id") else "✗ NO")
    with col3:
        st.metric("WhatsApp Connected", "✓ YES" if st.session_state.get("whatsapp_webhook_url") else "✗ NO")
    with col4:
        st.metric("Alert Types", 5)
    
    st.divider()
    
    # Telegram Configuration
    st.markdown("### 🤖 Telegram Configuration")
    st.caption("Set up Telegram bot to receive real-time alerts on your phone.")
    
    config_col_1, config_col_2 = st.columns(2)
    with config_col_1:
        telegram_token = st.text_input(
            "Telegram Bot Token",
            value=st.session_state.get("telegram_token", ""),
            type="password",
            help="Create a bot with @BotFather on Telegram to get a token.",
            key="telegram_token_input"
        )
        st.session_state.telegram_token = telegram_token.strip()
    
    with config_col_2:
        telegram_chat_id = st.text_input(
            "Telegram Chat ID",
            value=st.session_state.get("telegram_chat_id", ""),
            type="password",
            help="Forward a message from @userinfobot to get your Chat ID.",
            key="telegram_chat_id_input"
        )
        st.session_state.telegram_chat_id = telegram_chat_id.strip()

    whatsapp_webhook_url = st.text_input(
        "WhatsApp Webhook URL",
        value=st.session_state.get("whatsapp_webhook_url", ""),
        type="password",
        help="Optional: webhook URL from your WhatsApp automation provider. It should accept JSON with a 'message' field.",
        key="whatsapp_webhook_url_input",
    )
    st.session_state.whatsapp_webhook_url = whatsapp_webhook_url.strip()
    
    if (
        (st.session_state.get("telegram_token") and st.session_state.get("telegram_chat_id"))
        or st.session_state.get("whatsapp_webhook_url")
    ):
        col_test_1, col_test_2 = st.columns([3, 1])
        with col_test_1:
            pass
        with col_test_2:
            if st.button("📤 Test Connection", use_container_width=True):
                alerts_service = get_alerts_service(
                    st.session_state.telegram_token,
                    st.session_state.telegram_chat_id,
                    st.session_state.whatsapp_webhook_url,
                )
                success = alerts_service.send_test_alert()
                if success:
                    st.success("✅ Test alert sent. Check your configured channel.")
                else:
                    st.error("❌ Connection failed. Check your alert channel settings.")
    
    st.divider()
    
    # Alert Types Configuration
    st.markdown("### 🎯 Alert Types")
    st.caption("Choose which alerts you want to receive.")
    
    alerts_col_1, alerts_col_2 = st.columns(2)
    
    with alerts_col_1:
        st.session_state.alerts_enabled = st.toggle(
            "Enable All Alerts",
            value=bool(st.session_state.get("alerts_enabled", False)),
            help="Master switch to enable/disable all alerts",
            key="alerts_enabled_toggle"
        )
        
        if st.session_state.alerts_enabled:
            st.session_state.alert_breakout = st.checkbox(
                "⚡ Breakout Alerts",
                value=bool(st.session_state.get("alert_breakout", True)),
                help="Alert when stocks break key resistance levels",
                key="alert_breakout_check"
            )
            
            st.session_state.alert_pullback = st.checkbox(
                "📉 Pullback/Reversal Alerts",
                value=bool(st.session_state.get("alert_pullback", True)),
                help="Alert when stocks pullback to support levels",
                key="alert_pullback_check"
            )
            
            st.session_state.alert_entry_price_hit = st.checkbox(
                "🎯 Entry Price Hit",
                value=bool(st.session_state.get("alert_entry_price_hit", True)),
                help="Alert when your watchlist entry price is reached",
                key="alert_entry_price_check"
            )
    
    with alerts_col_2:
        st.session_state.alert_pre_breakout_score = st.slider(
            "Pre-Breakout Setup Score Threshold",
            min_value=3,
            max_value=10,
            value=int(st.session_state.get("alert_pre_breakout_score", 7)),
            help="Alert when pre-breakout setup score exceeds this value (0-10)",
            key="alert_prebreakout_slider",
            disabled=not st.session_state.get("alerts_enabled")
        )
        
        st.session_state.alert_target_hit = st.checkbox(
            "🎁 Profit Target Hit",
            value=bool(st.session_state.get("alert_target_hit", True)),
            help="Alert when positions reach profit targets",
            key="alert_target_check",
            disabled=not st.session_state.get("alerts_enabled")
        )
        
        st.session_state.alert_stop_hit = st.checkbox(
            "🛑 Stop Loss Hit",
            value=bool(st.session_state.get("alert_stop_hit", True)),
            help="Alert when positions hit stop losses",
            key="alert_stop_check",
            disabled=not st.session_state.get("alerts_enabled")
        )
    
    st.divider()
    
    # Trailing Stops Configuration
    st.markdown("### 🎚️ Trailing Stop Management")
    st.caption("Automatically manage position exits using ATR-based trailing stops.")
    
    trailing_col_1, trailing_col_2, trailing_col_3 = st.columns(3)
    
    with trailing_col_1:
        st.session_state.trailing_stops_enabled = st.toggle(
            "Enable Trailing Stops",
            value=bool(st.session_state.get("trailing_stops_enabled", False)),
            help="Track positions with dynamic trailing stops",
            key="trailing_stops_toggle"
        )
    
    with trailing_col_2:
        st.session_state.trailing_stop_atr_multiplier = st.number_input(
            "ATR Multiplier",
            min_value=0.5,
            max_value=3.0,
            value=float(st.session_state.get("trailing_stop_atr_multiplier", 1.5)),
            step=0.1,
            help="Distance from peak = ATR × this multiplier",
            key="atr_multiplier_input",
            disabled=not st.session_state.get("trailing_stops_enabled")
        )
    
    with trailing_col_3:
        st.session_state.trailing_stop_max_profit_pct = st.number_input(
            "Lock-in Profit %",
            min_value=1.0,
            max_value=50.0,
            value=float(st.session_state.get("trailing_stop_max_profit_pct", 5.0)),
            step=0.5,
            help="Lock in profits after reaching this % gain",
            key="lock_profit_input",
            disabled=not st.session_state.get("trailing_stops_enabled")
        )
    
    st.caption(f"When a position gains {st.session_state.get('trailing_stop_max_profit_pct', 5.0)}%, trailing stop will lock in the profit.")
    
    st.divider()
    
    # Active Trailing Stops
    st.markdown("### 📊 Active Trailing Stops")
    
    trailing_stops = st.session_state.get("trailing_stop_positions", [])
    
    if trailing_stops:
        # Display active trailing stops
        for position in trailing_stops:
            status = position.get("status", "ACTIVE")
            with st.expander(f"📈 {position.get('ticker', 'N/A')} @ ₹{position.get('entry_price', 0):.2f} · {status}", expanded=False):
                metrics_col_1, metrics_col_2, metrics_col_3, metrics_col_4 = st.columns(4)
                
                with metrics_col_1:
                    st.metric(
                        "Entry Price",
                        f"₹{position.get('entry_price', 0):.2f}"
                    )
                
                with metrics_col_2:
                    st.metric(
                        "Current Price",
                        f"₹{position.get('current_price', 0):.2f}",
                        delta=f"{position.get('pnl_pct', 0):.1f}%"
                    )
                
                with metrics_col_3:
                    st.metric(
                        "Trailing Stop",
                        f"₹{position.get('trailing_stop', 0):.2f}"
                    )
                
                with metrics_col_4:
                    st.metric(
                        "P&L",
                        f"₹{position.get('pnl', 0):.0f}",
                        delta=f"₹{position.get('distance_to_stop', 0):.2f} to stop"
                    )

                if status == "STOPPED_OUT":
                    st.error("Trailing stop hit. Review the position before taking further action.")
                
                # Remove position button
                if st.button("🗑️ Remove Trailing Stop", key=f"remove_{position.get('ticker')}"):
                    st.session_state.trailing_stop_positions.remove(position)
                    st.rerun()
    else:
        st.info("📌 No active trailing stops. Add positions from the Portfolio tab to start tracking them.")
    
    st.divider()
    
    # Intraday Scanning Configuration
    st.markdown("### 📊 Intraday Scanning")
    st.caption("Intraday intervals are available from the Scanner sidebar Timeframe control.")
    
    intraday_col_1, intraday_col_2 = st.columns(2)
    
    with intraday_col_1:
        st.session_state.intraday_timeframes = st.multiselect(
            "Preferred Intraday Timeframes",
            options=["Daily", "60m", "30m", "15m", "5m"],
            default=st.session_state.get("intraday_timeframes", ["Daily"]),
            help="Saved preference only. Run scans from the Scanner sidebar.",
            key="intraday_timeframes_select",
        )
    
    with intraday_col_2:
        st.info("Select the active scan interval in the Scanner sidebar before running a fresh scan.")
    
    st.divider()
    
    # Save Configuration
    st.markdown("### 💾 Configuration")
    
    save_info = st.info("✅ Configuration auto-saved to session")
    
    if st.button("📋 Show Current Configuration", use_container_width=True):
        config = {
            "alerts_enabled": st.session_state.get("alerts_enabled"),
            "telegram_configured": bool(st.session_state.get("telegram_chat_id")),
            "alert_types": {
                "breakout": st.session_state.get("alert_breakout"),
                "pullback": st.session_state.get("alert_pullback"),
                "pre_breakout_threshold": st.session_state.get("alert_pre_breakout_score"),
                "target_hit": st.session_state.get("alert_target_hit"),
                "stop_hit": st.session_state.get("alert_stop_hit"),
            },
            "trailing_stops": {
                "enabled": st.session_state.get("trailing_stops_enabled"),
                "atr_multiplier": st.session_state.get("trailing_stop_atr_multiplier"),
                "lock_in_profit_pct": st.session_state.get("trailing_stop_max_profit_pct"),
            },
        }
        st.json(config)
