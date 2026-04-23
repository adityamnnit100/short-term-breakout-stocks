"""Notes tab UI for user scratchpad."""

import datetime
import streamlit as st
from alphascanner_ui.auth import get_current_user
from alphascanner_ui.database import get_all_notes, save_note, delete_note

def render_tab() -> None:
    st.markdown('<div class="glass-card"><div class="panel-title" style="color: #00e5ff;">Notes & Strategy Scratchpad</div></div>', unsafe_allow_html=True)
    user = get_current_user()

    # Input section
    with st.expander("📝 Create New Note", expanded=True):
        note_title = st.text_input("Title", placeholder="e.g., Weekly Market View", key="new_note_title")
        note_content = st.text_area("Content", placeholder="Enter your observation or trade plan...", height=150, key="new_note_content")
        
        if st.button("💾 Save Note", use_container_width=True):
            if note_content.strip():
                note_id = str(datetime.datetime.now().timestamp())
                save_note(user, note_id, note_title or "Untitled Note", note_content)
                st.success("Note saved!")
                st.rerun()

    st.divider()

    # Display section
    notes = get_all_notes(user)
    if not notes:
        st.info("Your scratchpad is empty. Create your first note above.")
        return

    for i, note in enumerate(notes):
        with st.container():
            st.markdown(f"""
                <div class="glass-card" style="margin-bottom: 12px; border-left: 3px solid #00ffaa;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <strong style="color: #dffbff; font-size: 1.1rem;">{note['title']}</strong>
                        <span style="color: #94a3b8; font-size: 0.75rem;">{note['date']}</span>
                    </div>
                    <div style="color: #cbd5e1; margin-top: 8px; white-space: pre-wrap; font-size: 0.9rem;">{note['content']}</div>
                </div>
            """, unsafe_allow_html=True)
            
            if st.button(f"🗑 Delete Note", key=f"del_note_{note['id']}"):
                delete_note(user, note['id'])
                st.rerun()
