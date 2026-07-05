"""
Strategy Analyzer Tab: Connect to a Telegram group, fetch messages,
and analyze them to reverse-engineer a trading strategy.
"""
import asyncio
import pandas as pd
import re
import streamlit as st
from alphascanner_ui.services.telegram_client import get_telegram_client, fetch_messages_from_channel


def render_tab():
    st.markdown(
        '<div class="glass-card"><div class="panel-title" style="color: #00e5ff;">🔎 Strategy Analyzer</div>'
        '<p style="color:#cbd5e1;margin:0;">Analyze trade calls from a Telegram group to build a custom scanner.</p></div>',
        unsafe_allow_html=True,
    )

    # --- Configuration Section ---
    st.markdown("### 1. Telegram Connection")
    st.caption(
        "You need API credentials to connect as a user. Get them from [my.telegram.org](https://my.telegram.org). "
        "Your credentials and session are stored only in your browser's session state."
    )

    c1, c2 = st.columns(2)
    api_id = c1.text_input("API ID", key="sa_api_id", type="password")
    api_hash = c2.text_input("API Hash", key="sa_api_hash", type="password")

    # --- Authentication Flow ---
    client = get_telegram_client(api_id, api_hash, st.session_state.get("telethon_session"))

    if client and not client.is_connected():
        if "phone_code_hash" not in st.session_state:
            phone = st.text_input("Enter your phone number (e.g., +91...)", key="sa_phone")
            if st.button("Send Code"):
                with st.spinner("Sending verification code..."):
                    try:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        result = loop.run_until_complete(client.send_code_request(phone))
                        st.session_state.phone_code_hash = result.phone_code_hash
                        st.success("Code sent! Please check your Telegram app.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to send code: {e}")

        if "phone_code_hash" in st.session_state:
            code = st.text_input("Verification Code", key="sa_code")
            if st.button("Sign In"):
                with st.spinner("Signing in..."):
                    try:
                        loop = asyncio.get_event_loop()
                        loop.run_until_complete(
                            client.sign_in(
                                st.session_state.sa_phone,
                                code,
                                phone_code_hash=st.session_state.phone_code_hash,
                            )
                        )
                        st.session_state.telethon_session = client.session.save()
                        st.success("Signed in successfully!")
                        # Clean up state
                        del st.session_state["phone_code_hash"]
                        st.rerun()
                    except Exception as e:
                        st.error(f"Sign in failed: {e}")

    # --- Message Fetching Section ---
    if client and client.is_connected():
        st.success("✅ Connected to Telegram as a user.")
        st.markdown("### 2. Fetch & Analyze Messages")

        channel_name = st.text_input(
            "Telegram Channel/Group Name or ID",
            placeholder="e.g., 'MyTradingGroup' or -100123456789",
            key="sa_channel_name",
        )
        limit = st.slider("Number of messages to fetch", 50, 500, 100, key="sa_limit")

        if st.button("🚀 Fetch and Analyze", use_container_width=True):
            if not channel_name:
                st.warning("Please enter a channel name or ID.")
            else:
                with st.spinner(f"Fetching last {limit} messages from '{channel_name}'..."):
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)

                    messages, error = loop.run_until_complete(
                        fetch_messages_from_channel(client, channel_name, limit)
                    )

                    if error:
                        st.error(error)
                    elif messages:                        
                        st.success(f"Fetched {len(messages)} messages.")
                        df = pd.DataFrame(messages)
                        st.session_state.sa_messages = df
                        
                        # --- NEW: Parsing Logic ---
                        from alphascanner_ui.services.message_parser import parse_trade_signal
                        
                        with st.spinner("Parsing messages for trade signals..."):
                            parsed_data = [parse_trade_signal(text) for text in df['text']]
                            parsed_df = pd.DataFrame(parsed_data)
                            st.session_state.sa_parsed_messages = parsed_df

                        st.markdown("### 3. Parsed Trade Signals")
                        st.caption("The system's interpretation of the messages. Review for accuracy.")
                        st.dataframe(parsed_df[['ticker', 'signal', 'entry', 'stop_loss', 'targets', 'pattern']], use_container_width=True)

                        st.markdown("### 4. Raw Messages")
                        st.caption("The original messages fetched from the group.")
                        st.dataframe(df)
                    else:
                        st.info("No messages with text found in the specified channel.")
    else:
        st.info("Enter your API credentials above to connect to Telegram.")