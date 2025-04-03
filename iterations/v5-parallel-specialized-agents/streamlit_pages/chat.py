from langgraph.types import Command
import streamlit as st
import uuid
import sys
import os
import streamlit.components.v1 as components
import subprocess
from utils.utils import clear_thought_process, get_tp_socket, get_tp_command
from utils.subprocess_helper import is_thought_process_running, run_command
import threading

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from archon.archon_graph import agentic_flow

@st.cache_resource
def get_thread_id():
    return str(uuid.uuid4())

thread_id = get_thread_id()

async def run_agent_with_streaming(user_input: str):
    """
    Run the agent with streaming text for the user_input prompt,
    while maintaining the entire conversation in `st.session_state.messages`.
    """
    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }

    # First message from user
    if len(st.session_state.messages) == 1:
        async for msg in agentic_flow.astream(
                {"latest_user_message": user_input}, config, stream_mode="custom"
            ):
                yield msg
    # Continue the conversation
    else:
        async for msg in agentic_flow.astream(
            Command(resume=user_input), config, stream_mode="custom"
        ):
            yield msg

async def chat_tab():
    """Display the chat interface for talking to Archon"""
    st.write("Describe to me an AI agent you want to build and I'll code it for you with Pydantic AI.")
    st.write("Example: Build me an AI agent that can search the web with the Brave API.")

    # Initialize chat history in session state if not present
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    # if st.button("Show thought process"):
    
    
    # Add a clear conversation button
    if st.button("Clear Conversation"):
        st.session_state.messages = []
        clear_thought_process()
        st.rerun()

    # Display chat messages from history on app rerun
    for message in st.session_state.messages:
        message_type = message["type"]
        if message_type in ["human", "ai", "system"]:
            with st.chat_message(message_type):
                st.markdown(message["content"])    

    # Chat input for the user
    user_input = st.chat_input("What do you want to build today?")

    print(f"is_thought_process_running: {is_thought_process_running()}")
    if is_thought_process_running():
        components.iframe(get_tp_socket(), height=500, scrolling=False)
    if not user_input and not is_thought_process_running():
        if st.button("Click herer to inspect Archon's Decision Matrix ⚙️🧠💡"):
            print(get_tp_command())
            threading.Thread(target=run_command, args=(get_tp_command(),), daemon=True).start()
            st.rerun()

    if user_input:
        # We append a new request to the conversation explicitly
        st.session_state.messages.append({"type": "human", "content": user_input})
        
        # Display user prompt in the UI
        with st.chat_message("user"):
            st.markdown(user_input)

        # Display assistant response in chat message container
        response_content = ""
        with st.chat_message("assistant"):
            message_placeholder = st.empty()  # Placeholder for updating the message
            
            # Add a spinner while loading
            with st.spinner("Archon is thinking..."):
                # Run the async generator to fetch responses
                async for chunk in run_agent_with_streaming(user_input):
                    response_content += chunk
                    # Update the placeholder with the current response content
                    message_placeholder.markdown(response_content)
        
        st.session_state.messages.append({"type": "ai", "content": response_content})