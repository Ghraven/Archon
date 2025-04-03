import streamlit as st
import time
import os, sys
from pathlib import Path
# import math # Not strictly needed now

# --- Page Config (MUST BE FIRST Streamlit command) ---
st.set_page_config(layout="wide")

# --- Configuration ---
NUM_LINES_TO_SHOW = 5
POLL_INTERVAL = 1

# --- Path Setup ---
try:
    current_dir = os.path.dirname(os.path.abspath(__file__))
except NameError:
    current_dir = os.getcwd()
workbench_dir = os.path.join(current_dir, "workbench")
os.makedirs(workbench_dir, exist_ok=True)
default_poll_file_path = os.path.join(workbench_dir, "thought_process.txt")

# --- Initialize Session State ---
if "poll_file_path" not in st.session_state:
    st.session_state.poll_file_path = default_poll_file_path
if "is_polling" not in st.session_state:
    st.session_state.is_polling = True
if "last_error_message" not in st.session_state:
    st.session_state.last_error_message = None
if "last_content_display" not in st.session_state:
    st.session_state.last_content_display = ""
if "poll_counter" not in st.session_state:
    st.session_state.poll_counter = 0

# --- Ensure File Exists ---
poll_file = Path(st.session_state.poll_file_path)
if not poll_file.exists():
    try:
        poll_file.parent.mkdir(parents=True, exist_ok=True)
        with open(poll_file, "w", encoding='utf-8') as file:
            file.write("Energy levels optimal. Archon awaits your command... ✨⚡️\n")
    except Exception as e:
        st.error(f"Error creating initial file {poll_file}: {e}")
        st.stop()

# --- CSS for Glowing Effect (using color on a text character) ---
glowing_css = """
<style>
@keyframes glow {
  0% { color: darkgreen; text-shadow: 0 0 3px darkgreen; }
  50% { color: limegreen; text-shadow: 0 0 8px limegreen; } /* Brighter green */
  100% { color: darkgreen; text-shadow: 0 0 3px darkgreen; }
}

.glow-indicator {
  margin-bottom: 0.25em;
  font-size: 2.2em; /* Make the circle a bit bigger */
  vertical-align: middle; /* Align better with text */
  animation: glow 1.5s ease-in-out infinite;
  display: inline-block;
}
</style>
"""
st.markdown(glowing_css, unsafe_allow_html=True)

# --- App Layout ---

st.session_state.poll_interval = POLL_INTERVAL
if st.session_state.last_error_message:
    st.error(f"Last Error: {st.session_state.last_error_message}")

# --- Main Area ---
display_container = st.container(border=True)

with display_container:
    # --- Activity Indicator using CSS ---
    poll_cycle = st.session_state.poll_counter % 4
    indicator_dots = "." * (poll_cycle + 1)

    col1, col2 = st.columns([1, 10])
    with col1:
         # Added a text-shadow to the animation for a stronger glow effect
         st.markdown(f"<span class='glow-indicator'>●</span> **Archon🤖**", unsafe_allow_html=True)
    content_placeholder = st.empty()

# --- Core Polling and Display Logic ---
# (Keep the polling logic exactly the same as before)
if st.session_state.is_polling and st.session_state.poll_file_path:
    file_path_str = st.session_state.poll_file_path
    display_file_name = os.path.basename(file_path_str)

    try:
        p = Path(file_path_str)
        if not p.exists():
            st.session_state.last_error_message = f"File not found: {file_path_str}"
            content_placeholder.warning(f"⚠️ File not found: {display_file_name}. Retrying...")
            if st.session_state.last_content_display:
                st.text_area( # Display below warning
                    f"Last known content (last {NUM_LINES_TO_SHOW} lines)",
                    value=st.session_state.last_content_display, height=200,
                    key="last_file_content_area_warning", disabled=True
                )
        elif not p.is_file():
            st.session_state.last_error_message = f"Path exists but is not a file: {file_path_str}"
            content_placeholder.error(f"⚠️ Path is not a file: {display_file_name}. Please check the path.")
        else:
            full_content = p.read_text(encoding='utf-8', errors='ignore')
            lines = full_content.splitlines()
            last_lines = lines[-NUM_LINES_TO_SHOW:]
            current_content_display = "\n".join(last_lines)

            if current_content_display != st.session_state.last_content_display:
                 st.session_state.last_content_display = current_content_display
            st.session_state.last_error_message = None

            content_placeholder.text_area( # Update main area
                label=f"Displaying Last {NUM_LINES_TO_SHOW} thoughts",
                value=st.session_state.last_content_display, height=300,
                key="file_content_area", disabled=True
            )
    except Exception as e:
        error_msg = f"Error reading file {display_file_name}: {e}"
        st.session_state.last_error_message = error_msg
        content_placeholder.error(f"⚠️ {error_msg}")
        if st.session_state.last_content_display:
             st.text_area( # Display below error
                 f"Last known content (last {NUM_LINES_TO_SHOW} lines)",
                 value=st.session_state.last_content_display, height=200,
                 key="last_file_content_area_error", disabled=True
             )

    if st.session_state.is_polling:
        st.session_state.poll_counter += 1
        time.sleep(st.session_state.poll_interval)
        st.rerun()
else:
    st.info("Polling is currently stopped.")