"""Mainframe File Anonymizer — Streamlit entry point."""
import streamlit as st

from anonymizer.ui import steps

st.set_page_config(page_title="Mainframe File Anonymizer", page_icon="🛡️",
                   layout="wide")

STEP_NAMES = ["Upload", "Fields", "Masking", "Generate", "Preview"]
RENDERERS = [steps.render_upload, steps.render_fields, steps.render_rules,
             steps.render_generate, steps.render_preview]

if "step" not in st.session_state:
    st.session_state.step = 0

st.title("🛡️ Mainframe File Anonymizer")
st.caption("Mask sensitive data in mainframe files for safe use in test "
           "environments. Everything stays on this machine.")

cols = st.columns(len(STEP_NAMES))
for i, (col, name) in enumerate(zip(cols, STEP_NAMES)):
    marker = "🔵" if i == st.session_state.step else (
        "✅" if i < st.session_state.step else "⚪")
    col.markdown(f"{marker} **{i + 1}. {name}**")
st.divider()

RENDERERS[st.session_state.step]()
