"""Trade journal tab UI."""

import datetime

import pandas as pd
import streamlit as st


def render_tab() -> None:
    st.markdown('<div class="glass-card"><div class="panel-title" style="color: #00e5ff;">Trade Journal</div></div>', unsafe_allow_html=True)

    with st.expander("➕ Log New Trade", expanded=False):
        col_1, col_2, col_3 = st.columns(3)
        ticker = col_1.text_input("Ticker", key="tj_t").upper()
        entry_date = col_1.date_input("Entry Date", datetime.date.today(), key="tj_ed")
        entry_price = col_2.number_input("Entry Price", min_value=0.0, step=0.01, key="tj_ep")
        exit_date = col_2.date_input("Exit Date", value=None, key="tj_xd")
        exit_price = col_3.number_input("Exit Price", min_value=0.0, step=0.01, key="tj_xp")
        quantity = col_3.number_input("Quantity", min_value=1, step=1, key="tj_q")
        pattern = st.selectbox(
            "Pattern",
            ["52W High", "Range Breakout", "Flag & Pole", "Cup & Handle", "Triangle BO", "Other"],
            key="tj_pat",
        )
        notes = st.text_area("Notes", height=80, key="tj_n")

        if st.button("💾 Save Trade"):
            if ticker and entry_price > 0 and quantity > 0:
                st.session_state.trade_journal.append(
                    {
                        "ticker": ticker,
                        "entry_date": str(entry_date),
                        "entry": entry_price,
                        "exit_date": str(exit_date) if exit_date else None,
                        "exit": exit_price,
                        "qty": quantity,
                        "pattern": pattern,
                        "notes": notes,
                        "pnl": (exit_price - entry_price) * quantity if exit_price > 0 else 0,
                        "status": "Closed" if exit_price > 0 else "Open",
                    }
                )
                st.success(f"Saved trade for {ticker}!")
                st.rerun()
            else:
                st.error("Fill in ticker, entry price and quantity.")

    journal = st.session_state.trade_journal
    if not journal:
        st.info("No trades logged yet.")
        return

    journal_df = pd.DataFrame(journal)
    total_trades = len(journal_df)
    winning_trades = int((journal_df["pnl"] > 0).sum())
    losing_trades = int((journal_df["pnl"] < 0).sum())
    win_rate = winning_trades / total_trades * 100 if total_trades > 0 else 0
    total_pnl = journal_df["pnl"].sum()

    metrics = st.columns(4)
    metrics[0].metric("Total Trades", total_trades)
    metrics[1].metric("Win Rate", f"{win_rate:.1f}%")
    metrics[2].metric("Wins / Losses", f"{winning_trades} / {losing_trades}")
    metrics[3].metric("Total P&L", f"₹{total_pnl:,.0f}", delta=f"₹{total_pnl:+,.0f}")

    st.dataframe(
        journal_df[["ticker", "entry_date", "entry", "exit", "qty", "pattern", "pnl", "status"]],
        use_container_width=True,
        hide_index=True,
    )

    csv = journal_df.to_csv(index=False).encode()
    st.download_button("📥 Export Journal CSV", csv, f"journal_{datetime.date.today()}.csv", "text/csv")
