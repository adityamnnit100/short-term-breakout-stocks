"""Notes tab UI for user scratchpad."""

import datetime
import streamlit as st
from alphascanner_ui.auth import save_current_user_workspace

def render_tab() -> None:
    st.markdown('<div class="glass-card"><div class="panel-title" style="color: #00e5ff;">Notes & Strategy Scratchpad</div></div>', unsafe_allow_html=True)

    # Input section
    with st.expander("📝 Create New Note", expanded=True):
        note_title = st.text_input("Title", placeholder="e.g., Weekly Market View", key="new_note_title")
        note_content = st.text_area("Content", placeholder="Enter your observation or trade plan...", height=150, key="new_note_content")
        
        if st.button("💾 Save Note", use_container_width=True):
            if note_content.strip():
                new_note = {
                    "id": str(datetime.datetime.now().timestamp()),
                    "title": note_title if note_title else "Untitled Note",
                    "content": note_content,
                    "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                }
                st.session_state.notes.insert(0, new_note)
                save_current_user_workspace()
                st.success("Note saved!")
                st.rerun()
            else:
                st.error("Please enter some content.")

    st.divider()

    # Display section
    notes = st.session_state.get("notes", [])
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
                st.session_state.notes.pop(i)
                save_current_user_workspace()
                st.rerun()
