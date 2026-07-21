import os
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

st.set_page_config(page_title="Advisor Chat", page_icon="💬", layout="wide")
st.title("💬 Advisor Chat")
st.caption("M6 — CrewAI agent. Every factual claim it makes comes from a tool call, not from its own memory.")

provider = os.getenv("LLM_PROVIDER", "groq")
key_env_var = {"groq": "GROQ_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}.get(provider, "")
key_present = bool(os.getenv(key_env_var))

if not key_present:
    st.error(
        f"No API key found for LLM_PROVIDER='{provider}'. Copy `.env.example` to `.env` "
        f"and set the matching key, then restart the app.",
        icon="🔑",
    )
    st.stop()

from backend.agent import run_advisor_query

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []  # list of {"role": "user"/"assistant", "content": str, "tool_calls": [...]}

for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if msg["role"] == "assistant" and msg.get("tool_calls"):
            with st.expander(f"Tool calls made ({len(msg['tool_calls'])})"):
                for call in msg["tool_calls"]:
                    st.write(f"**{call['tool']}**")
                    st.json({"input": call["input"], "output": call["output"]})

user_input = st.chat_input("Ask about your schedule, requirements, or a substitution...")

if user_input:
    st.session_state.chat_history.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.write(user_input)

    history_strings = [
        f"{m['role']}: {m['content']}" for m in st.session_state.chat_history[:-1]
    ]

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            result = run_advisor_query(user_input, conversation_history=history_strings)
        st.write(result["response"])
        if result["tool_calls"]:
            with st.expander(f"Tool calls made ({len(result['tool_calls'])})"):
                for call in result["tool_calls"]:
                    st.write(f"**{call['tool']}**")
                    st.json({"input": call["input"], "output": call["output"]})

    st.session_state.chat_history.append(
        {"role": "assistant", "content": result["response"], "tool_calls": result["tool_calls"]}
    )
