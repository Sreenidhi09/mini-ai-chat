import streamlit as st
import requests

API_BASE = "https://mini-ai-chat-wfvn.onrender.com"

st.set_page_config(
    page_title="Mini AI Chat",
    page_icon="🤖",
    layout="wide",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Sidebar */
section[data-testid="stSidebar"] {
    background: #1a1a2e;
    color: white;
}
section[data-testid="stSidebar"] * {
    color: white !important;
}
/* Chat bubbles */
.user-bubble {
    background: #0f3460;
    color: white;
    padding: 10px 16px;
    border-radius: 18px 18px 4px 18px;
    margin: 6px 0 6px auto;
    max-width: 75%;
    width: fit-content;
    margin-left: auto;
}
.ai-bubble {
    background: #16213e;
    color: #e0e0e0;
    padding: 10px 16px;
    border-radius: 18px 18px 18px 4px;
    margin: 6px auto 6px 0;
    max-width: 75%;
    width: fit-content;
}
.thread-label {
    font-size: 12px;
    color: #888;
    margin-bottom: 2px;
}
</style>
""", unsafe_allow_html=True)


# ── Helpers ────────────────────────────────────────────────────────────────────
def api(method: str, path: str, **kwargs):
    try:
        r = getattr(requests, method)(f"{API_BASE}{path}", **kwargs)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        st.error("❌ Cannot connect to the backend. Make sure `uvicorn main:app` is running.")
        st.stop()
    except Exception as e:
        st.error(f"API error: {e}")
        return None


def fetch_threads():
    return api("get", "/threads") or []


def create_thread(title="New Thread"):
    return api("post", "/threads", json={"title": title})


def delete_thread(tid: int):
    api("delete", f"/threads/{tid}")


def fetch_messages(tid: int):
    return api("get", f"/threads/{tid}/messages") or []


def send_message(tid: int, text: str):
    return api("post", "/chat", json={"thread_id": tid, "user_message": text})


# ── Session defaults ───────────────────────────────────────────────────────────
if "active_thread_id" not in st.session_state:
    st.session_state.active_thread_id = None
if "pending_input" not in st.session_state:
    st.session_state.pending_input = ""


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🤖 Mini AI Chat")
    st.markdown("---")

    if st.button("➕  New Thread", use_container_width=True):
        new = create_thread()
        if new:
            st.session_state.active_thread_id = new["id"]
            st.rerun()

    st.markdown("### Threads")
    threads = fetch_threads()

    if not threads:
        st.info("No threads yet. Click **New Thread** to start.")
    else:
        for t in threads:
            col1, col2 = st.columns([5, 1])
            is_active = st.session_state.active_thread_id == t["id"]
            label = ("▶ " if is_active else "") + t["title"]
            with col1:
                if st.button(label, key=f"t_{t['id']}", use_container_width=True):
                    st.session_state.active_thread_id = t["id"]
                    st.rerun()
            with col2:
                if st.button("🗑", key=f"d_{t['id']}"):
                    delete_thread(t["id"])
                    if st.session_state.active_thread_id == t["id"]:
                        st.session_state.active_thread_id = None
                    st.rerun()

    st.markdown("---")
    st.caption("Universal memory ON — AI remembers all threads 🧠")


# ── Main chat area ─────────────────────────────────────────────────────────────
if st.session_state.active_thread_id is None:
    st.markdown("""
    <div style='text-align:center; padding-top:120px; color:#888;'>
        <h2>👈 Select or create a thread to start chatting</h2>
        <p>Your AI has universal memory — it remembers conversations across all threads.</p>
    </div>
    """, unsafe_allow_html=True)
else:
    tid = st.session_state.active_thread_id

    # Find thread title
    thread_title = next((t["title"] for t in threads if t["id"] == tid), f"Thread {tid}")
    st.markdown(f"### 💬 {thread_title}")
    st.markdown("---")

    messages = fetch_messages(tid)

    # Chat history
    chat_container = st.container()
    with chat_container:
        if not messages:
            st.markdown(
                "<div style='text-align:center;color:#666;padding:60px 0'>No messages yet. Say something! 👋</div>",
                unsafe_allow_html=True,
            )
        for msg in messages:
            if msg["role"] == "user":
                st.markdown(
                    f"<div class='user-bubble'>🧑 {msg['content']}</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"<div class='ai-bubble'>🤖 {msg['content']}</div>",
                    unsafe_allow_html=True,
                )

    st.markdown("---")

    # Input row
    col_in, col_btn = st.columns([8, 1])
    with col_in:
        user_input = st.text_input(
            "Your message",
            value="",
            placeholder="Type a message and press Send…",
            label_visibility="collapsed",
            key="chat_input",
        )
    with col_btn:
        send = st.button("Send 🚀", use_container_width=True)

    if send and user_input.strip():
        with st.spinner("AI is thinking…"):
            send_message(tid, user_input.strip())
        st.rerun()