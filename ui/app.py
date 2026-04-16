import streamlit as st
import requests
import time
import os

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")

st.set_page_config(page_title="Coaction Bot", page_icon="✦", layout="wide")

st.markdown("""
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}

/* ── Global reset ── */
body, .stApp { background: #ffffff; }

/* ── Chat container ── */
.chat-area {
    max-width: 1100px;
    margin: 0 auto;
    padding: 1.5rem 1rem 6rem 1rem;
    display: flex;
    flex-direction: column;
    gap: 1.8rem;
}

/* ── User message (right-aligned pill) ── */
.user-row {
    display: flex;
    justify-content: flex-end;
}
.user-bubble {
    background: #f0f0f0;
    color: #1a1a1a;
    padding: 0.55rem 1.1rem;
    border-radius: 20px;
    font-size: 0.95rem;
    max-width: 65%;
    line-height: 1.5;
    word-wrap: break-word;
}

/* ── Bot message (left-aligned with header) ── */
.bot-block { display: flex; flex-direction: column; gap: 0.4rem; }
.bot-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-weight: 600;
    font-size: 0.95rem;
    color: #1a1a1a;
}
.bot-icon {
    width: 28px; height: 28px;
    background: #e8e8e8;
    border-radius: 6px;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.85rem;
}
.bot-text {
    font-size: 0.95rem;
    color: #1a1a1a;
    line-height: 1.65;
    padding-left: 0.2rem;
    white-space: pre-wrap;
    word-wrap: break-word;
}

/* ── Sources (collapsible) ── */
.sources-toggle {
    margin-top: 0.5rem;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    overflow: hidden;
    font-size: 0.8rem;
}
.sources-toggle summary {
    cursor: pointer;
    padding: 0.4rem 0.7rem;
    color: #6b7280;
    font-weight: 500;
    list-style: none;
    display: flex;
    align-items: center;
    gap: 0.35rem;
    user-select: none;
}
.sources-toggle summary::-webkit-details-marker { display: none; }
.sources-toggle summary::before {
    content: '▶';
    font-size: 0.55rem;
    transition: transform 0.2s ease;
    display: inline-block;
}
.sources-toggle[open] summary::before {
    transform: rotate(90deg);
}
.sources-toggle .sources-links {
    padding: 0.3rem 0.7rem 0.5rem 1.4rem;
    border-top: 1px solid #f3f4f6;
}
.sources-toggle .sources-links a {
    color: #2563eb; text-decoration: none;
    display: block; margin: 2px 0;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    font-size: 0.78rem;
}
.sources-toggle .sources-links a:hover { text-decoration: underline; }

/* ── Follow-up pills (right-aligned, compact) ── */
.followup-row {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 0.15rem;
    margin-top: 0.3rem;
}

/* ── Thinking dots ── */
.thinking-dots { display: flex; gap: 5px; padding: 0.3rem 0; }
.dot {
    width: 7px; height: 7px; border-radius: 50%;
    background: #9ca3af;
    animation: bounce 1.2s infinite ease-in-out;
}
.dot:nth-child(2) { animation-delay: 0.2s; }
.dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce {
    0%,80%,100% { transform: translateY(0); opacity: 0.4; }
    40%          { transform: translateY(-5px); opacity: 1; }
}

/* ── Welcome screen ── */
.welcome {
    text-align: center;
    padding: 3rem 1rem 1.5rem;
    color: #6b7280;
}
.welcome h2 { color: #111827; font-size: 1.5rem; margin-bottom: 0.4rem; }
.welcome p  { font-size: 0.93rem; }

/* ── Suggestion grid buttons ── */
div[data-testid="stButton"] > button {
    border-radius: 12px !important;
    border: 1px solid #e5e7eb !important;
    background: #fafafa !important;
    color: #374151 !important;
    font-size: 0.88rem !important;
    padding: 0.5rem 0.9rem !important;
    transition: background 0.15s;
}
div[data-testid="stButton"] > button:hover {
    background: #f3f4f6 !important;
    border-color: #d1d5db !important;
}

/* ── Follow-up buttons specifically (horizontal pills) ── */
.fu-btn > div[data-testid="stButton"] {
    display: flex !important;
    justify-content: center !important;
}
.fu-btn > div[data-testid="stButton"] > button {
    border-radius: 12px !important;
    background: #ffffff !important;
    border: 1px solid #d1d5db !important;
    color: #374151 !important;
    font-size: 0.78rem !important;
    padding: 0.3rem 0.6rem !important;
    white-space: normal !important;
    width: 100% !important;
    line-height: 1.35 !important;
    min-height: 40px !important;
    text-align: center !important;
}
.fu-btn > div[data-testid="stButton"] > button:hover {
    background: #f9fafb !important;
}

/* ── Chat input box (wide — spans full chat area) ── */
div[data-testid="stChatInput"] {
    position: fixed;
    bottom: 0; left: 0; right: 0;
    background: #ffffff !important;
    padding: 0.6rem 1rem 0.8rem;
    border-top: 1px solid #f3f4f6;
    z-index: 100;
    box-shadow: none !important;
}
div[data-testid="stChatInput"] > div {
    max-width: 1100px;
    width: 100% !important;
    background: #ffffff !important;
    box-shadow: none !important;
    margin: 0 auto;
    display: flex !important;
    align-items: center !important;
}
div[data-testid="stChatInput"] textarea {
    border-radius: 12px !important;
    border: 1px solid #e5e7eb !important;
    background: #fafafa !important;
    font-size: 0.93rem !important;
    padding: 0.6rem 0.9rem !important;
    min-height: unset !important;
    box-shadow: none !important;
}
div[data-testid="stChatInput"] button {
    position: relative !important;
    bottom: unset !important;
    margin-left: 0.5rem !important;
    flex-shrink: 0 !important;
}
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────
if "messages"   not in st.session_state: st.session_state.messages   = []
if "session_id" not in st.session_state: st.session_state.session_id = None
if "jobs"       not in st.session_state: st.session_state.jobs       = []
if "thinking"   not in st.session_state: st.session_state.thinking   = False

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ✦ Coaction Bot")
    st.caption("Powered by your content")
    st.divider()

    st.subheader("⚙️ Settings")
    max_depth = st.slider("Crawl depth", 1, 5, 2)
    max_pages = st.slider("Max pages", 5, 200, 50)
    top_k     = st.slider("Results to retrieve", 1, 20, 5)

    st.divider()
    kb_id = os.getenv("BEDROCK_KB_ID", "")
    st.caption(f"KB ID from env: `{kb_id}`" if kb_id else "KB ID from env: not set")
    st.divider()
    try:
        r = requests.get(API_BASE.replace("/api/v1", "/health"), timeout=3)
        st.success("API online", icon="✅") if r.ok else st.warning("API degraded", icon="⚠️")
    except Exception:
        st.error("API unreachable", icon="❌")

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_crawl, tab_chat = st.tabs(["🌐 Ingest Content", "💬 Ask Questions"])


# ── TAB 1: Crawl ──────────────────────────────────────────────────────────────
with tab_crawl:
    st.header("Ingest a Website")
    st.write("Crawl a URL and add its content to the knowledge base.")

    url_input = st.text_input("URL", placeholder="https://docs.example.com", label_visibility="collapsed")
    col1, _ = st.columns([1, 5])
    with col1:
        crawl_btn = st.button("🚀 Start Crawl", type="primary", use_container_width=True)

    if crawl_btn:
        if not url_input.strip():
            st.warning("Please enter a URL.")
        else:
            with st.spinner("Submitting crawl job..."):
                try:
                    resp = requests.post(
                        f"{API_BASE}/crawl",
                        json={"url": url_input, "max_depth": max_depth, "max_pages": max_pages},
                        timeout=10,
                    )
                    resp.raise_for_status()
                    job = resp.json()
                except Exception as e:
                    st.error(f"Failed to submit job: {e}")
                    st.stop()

            job_id = job["job_id"]
            st.info(f"Job started · ID: `{job_id}`")
            progress  = st.progress(0, text="Crawling...")
            status_ph = st.empty()
            step, poll = 0, {}
            max_wait_seconds = 1800  # 30 minutes
            elapsed = 0

            while elapsed < max_wait_seconds:
                time.sleep(3)
                elapsed += 3
                try:
                    poll = requests.get(f"{API_BASE}/crawl/{job_id}", timeout=10).json()
                except Exception:
                    status_ph.caption("Waiting for backend...")
                    continue
                pct = min(10 + int(elapsed / max_wait_seconds * 85), 95)
                progress.progress(pct, text=f"Status: {poll.get('status', 'crawling')}  ({elapsed}s elapsed)")
                status_ph.caption(poll.get("message", ""))
                if poll.get("status") in ("done", "failed"):
                    break

            progress.progress(100)
            if poll.get("status") == "done":
                st.success(f"✅ Done — **{poll['pages_crawled']} pages** crawled, **{poll['chunks_indexed']} chunks** indexed.")
                st.info("Now run ingestion from AWS Bedrock console for your data source.")
                st.session_state.jobs.insert(0, {"url": url_input, "job_id": job_id})
            else:
                st.error(f"❌ Failed: {poll.get('message', 'Unknown error')}")

    st.divider()
    st.subheader("Recent Jobs")
    if st.session_state.jobs:
        for j in st.session_state.jobs[:5]:
            st.code(f"{j['url']}  →  {j['job_id']}", language=None)
    else:
        st.caption("No jobs yet.")


# ── TAB 2: Chat ───────────────────────────────────────────────────────────────
with tab_chat:

    # Clear button
    if st.session_state.messages:
        col_clear, _ = st.columns([1, 8])
        with col_clear:
            if st.button("🗑️ Clear", key="clear_chat"):
                st.session_state.messages   = []
                st.session_state.session_id = None
                st.rerun()

    # ── Render messages ──
    for idx, msg in enumerate(st.session_state.messages):
        is_last = idx == len(st.session_state.messages) - 1

        if msg["role"] == "user":
            st.markdown(f"""
<div class="chat-area" style="padding-bottom:0;gap:0;">
  <div class="user-row">
    <div class="user-bubble">{msg["content"]}</div>
  </div>
</div>""", unsafe_allow_html=True)

        else:
            # Sources HTML (collapsible)
            sources_html = ""
            if msg.get("sources"):
                links = "".join(
                    f'<a href="{s}" target="_blank">{s}</a>' for s in msg["sources"]
                )
                sources_html = (
                    f'<details class="sources-toggle">'
                    f'<summary>📎 Sources</summary>'
                    f'<div class="sources-links">{links}</div>'
                    f'</details>'
                )

            st.markdown(f"""
<div class="chat-area" style="padding-bottom:0;gap:0;">
  <div class="bot-block">
    <div class="bot-header">
      <div class="bot-icon">✦</div>
      Coaction Bot
    </div>
    <div class="bot-text">{msg["content"]}</div>
    {sources_html}
  </div>
</div>""", unsafe_allow_html=True)

            # Follow-up questions as horizontal pills labeled "Suggested questions"
            if is_last and msg.get("follow_up_questions"):
                fu_cols = st.columns(len(msg["follow_up_questions"]))
                st.markdown('<div style="text-align:right; font-size:0.78rem; color:#9ca3af; margin-bottom:0.2rem;">Suggested questions</div>', unsafe_allow_html=True)
                for i, q in enumerate(msg["follow_up_questions"]):
                    with fu_cols[i]:
                        st.markdown('<div class="fu-btn">', unsafe_allow_html=True)
                        if st.button(q, key=f"fu_{idx}_{i}", use_container_width=True):
                            st.session_state["pending_prompt"] = q
                            st.rerun()
                        st.markdown('</div>', unsafe_allow_html=True)

    # Thinking indicator
    if st.session_state.thinking:
        st.markdown("""
<div class="chat-area" style="padding-bottom:0;gap:0;">
  <div class="bot-block">
    <div class="bot-header">
      <div class="bot-icon">✦</div>
      Coaction Bot
    </div>
    <div class="thinking-dots">
      <div class="dot"></div><div class="dot"></div><div class="dot"></div>
    </div>
  </div>
</div>""", unsafe_allow_html=True)

    # ── Welcome screen ──
    if not st.session_state.messages and not st.session_state.thinking:
        st.markdown("""
<div class="welcome">
  <h2>How can I help you?</h2>
</div>""", unsafe_allow_html=True)

    # ── Chat input ──
    prompt = st.session_state.pop("pending_prompt", None) or st.chat_input("Message Coaction Bot")

    if prompt and not st.session_state.thinking:
        if not st.session_state.session_id:
            try:
                sess = requests.post(f"{API_BASE}/session/create", json={}, timeout=5).json()
                st.session_state.session_id = sess.get("session_id")
            except Exception:
                pass

        st.session_state.messages.append({"role": "user", "content": prompt})
        st.session_state.thinking = True
        st.rerun()

    # ── Process response ──
    if st.session_state.thinking:
        try:
            resp = requests.post(
                f"{API_BASE}/query",
                json={"query": st.session_state.messages[-1]["content"], "top_k": top_k, "session_id": st.session_state.session_id},
                timeout=60,
            )
            resp.raise_for_status()
            data                = resp.json()
            answer              = data["answer"]
            sources             = data.get("sources", [])
            follow_up_questions = data.get("follow_up_questions", [])
            if data.get("session_id"):
                st.session_state.session_id = data["session_id"]
        except Exception as e:
            answer              = f"Error: {e}"
            sources             = []
            follow_up_questions = []

        st.session_state.messages.append({
            "role": "assistant",
            "content": answer,
            "sources": sources,
            "follow_up_questions": follow_up_questions,
        })
        st.session_state.thinking = False
        st.rerun()
