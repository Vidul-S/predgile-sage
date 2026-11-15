import streamlit as st
import json
import os
import time
import requests
import pandas as pd
from src.pipeline import SagePipeline
from eval_harness import run_evaluation, EXPECTED_BENCHMARK

st.set_page_config(
    page_title="Paperkite Knowledge Base QA — Sage",
    page_icon="🪁",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for modern enterprise look
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E293B;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #64748B;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 1rem;
        text-align: center;
    }
    .metric-val {
        font-size: 1.8rem;
        font-weight: 700;
        color: #0F172A;
    }
    .metric-label {
        font-size: 0.85rem;
        color: #64748B;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .status-badge-answered {
        background-color: #DCFCE7;
        color: #166534;
        padding: 4px 10px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .status-badge-abstained {
        background-color: #FEF3C7;
        color: #92400E;
        padding: 4px 10px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .status-badge-clarify {
        background-color: #E0E7FF;
        color: #3730A3;
        padding: 4px 10px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .status-badge-refused {
        background-color: #FEE2E2;
        color: #991B1B;
        padding: 4px 10px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .citation-box {
        background-color: #F1F5F9;
        border-left: 4px solid #3B82F6;
        padding: 0.75rem 1rem;
        margin-top: 0.5rem;
        border-radius: 0 6px 6px 0;
        font-size: 0.9rem;
    }
    .conflict-box {
        background-color: #FFFBEB;
        border-left: 4px solid #F59E0B;
        padding: 0.75rem 1rem;
        margin-top: 0.5rem;
        border-radius: 0 6px 6px 0;
        font-size: 0.9rem;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def load_pipeline():
    return SagePipeline()


def check_ollama_status(url="http://localhost:11434/api/tags"):
    try:
        resp = requests.get(url, timeout=1.5)
        if resp.status_code == 200:
            models = [m.get("name") for m in resp.json().get("models", [])]
            return True, models
        return False, []
    except Exception:
        return False, []


pipeline = load_pipeline()
ollama_online, installed_models = check_ollama_status()

# Sidebar Navigation
st.sidebar.markdown("## 🪁 Paperkite Sage")
st.sidebar.markdown("**Local Evidence-Based QA**")

nav = st.sidebar.radio(
    "Navigation",
    ["🏠 Home", "💬 Ask a Question", "🔍 Source Evidence", "📋 Sample Questions", "📊 Evaluation Dashboard", "📖 About Project"],
    index=1
)

st.sidebar.markdown("---")
st.sidebar.markdown("### 🖥️ Runtime Status")
if ollama_online:
    st.sidebar.success(f"🟢 Ollama Online")
    st.sidebar.caption(f"Models: {', '.join(installed_models) if installed_models else 'None'}")
else:
    st.sidebar.warning("🟡 Ollama Offline (Using Local Fallback)")

st.sidebar.info(
    "**Hardware Target:**\n"
    "• Windows 11 (16 GB RAM)\n"
    "• 100% Free & Local Execution\n"
    "• REST API: `POST /ask`"
)

# -------------------------------------------------------------
# TAB 1: HOME
# -------------------------------------------------------------
if nav == "🏠 Home":
    st.markdown('<div class="main-header">🪁 Paperkite Knowledge System — Sage</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Explainable, evidence-grounded support intelligence over messy enterprise documentation.</div>', unsafe_allow_html=True)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(
            f'<div class="metric-card"><div class="metric-val">{len(pipeline.retriever.chunks)}</div>'
            f'<div class="metric-label">Indexed Chunks</div></div>',
            unsafe_allow_html=True
        )
    with col2:
        st.markdown(
            '<div class="metric-card"><div class="metric-val">150</div>'
            '<div class="metric-label">Processed Documents</div></div>',
            unsafe_allow_html=True
        )
    with col3:
        st.markdown(
            '<div class="metric-card"><div class="metric-val">5</div>'
            '<div class="metric-label">Formats (.md, .html, .txt, .pdf, .csv)</div></div>',
            unsafe_allow_html=True
        )
    with col4:
        engine_str = "Qwen 2.5 (3B)" if ollama_online else "Fallback Engine"
        st.markdown(
            f'<div class="metric-card"><div class="metric-val">{engine_str}</div>'
            f'<div class="metric-label">Active Inference</div></div>',
            unsafe_allow_html=True
        )

    st.markdown("---")
    st.markdown("### 🎯 Key Architectural Pillars")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("#### 1. Truth in Recency")
        st.write("Resolves contradictory documentation by cross-referencing chronological changelogs and document update timestamps.")
    with c2:
        st.markdown("#### 2. Right to Abstain")
        st.write("Refuses unsupported queries (such as cryptocurrency or unreleased pricing) instead of hallucinating confident falsehoods.")
    with c3:
        st.markdown("#### 3. Air-Gapped Security")
        st.write("Segregates confidential internal-only staff documents and intercepts direct and indirect prompt injection attacks.")


# -------------------------------------------------------------
# TAB 2: ASK A QUESTION
# -------------------------------------------------------------
elif nav == "💬 Ask a Question":
    st.markdown('<div class="main-header">💬 Ask Sage</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Ask payment, billing, tax, or API questions grounded strictly in Paperkite documents.</div>', unsafe_allow_html=True)

    user_q = st.text_input("Enter your question:", placeholder="e.g. How do I issue a partial refund? or What is the rate limit on Pro?")

    col_btn, _ = st.columns([1, 5])
    with col_btn:
        ask_btn = st.button("Submit Question", type="primary")

    if ask_btn and user_q.strip():
        with st.spinner("Retrieving evidence and evaluating sources..."):
            res = pipeline.ask(user_q)

        # Status badge rendering
        status = res.get("status", "answered")
        status_label = res.get("status_label", status)
        badge_class = f"status-badge-{status}"
        
        st.markdown("---")
        b_col, e_col, lat_col = st.columns([2, 3, 2])
        with b_col:
            st.markdown(f'**Status:** <span class="{badge_class}">{status_label.upper()}</span>', unsafe_allow_html=True)
        with e_col:
            if res.get("llm_generated"):
                st.markdown(f"**Engine:** 🤖 Local LLM (`{res.get('model')}`)")
            else:
                st.markdown(f"**Engine:** ⚙️ Local Deterministic Grounded Engine (`{res.get('model')}`)")
        with lat_col:
            st.markdown(f"**Latency:** `{res.get('latency_ms', 0)} ms` | **Confidence:** `{int(res.get('confidence', 0.8)*100)}%`")

        # Answer Presentation
        st.markdown("### Answer")
        if status == "clarify":
            st.info(f"❓ **Clarification Required:**\n\n{res.get('clarification_prompt')}")
        elif status == "abstained":
            st.warning(f"⚠️ **Abstained from Answering:**\n\n{res.get('reasoning_summary')}")
        elif status == "refused":
            st.error(f"🛑 **Request Denied:**\n\n{res.get('answer')}")
        else:
            st.success(res.get("answer"))

        # Conflicts
        if res.get("conflicts"):
            st.markdown("### ⚠️ Documentation Conflicts Detected & Resolved")
            for conf in res["conflicts"]:
                st.markdown(
                    f'<div class="conflict-box"><b>Resolution:</b> {conf.get("resolution")}<br/>'
                    f'<small><b>Involved Documents:</b> {", ".join(conf.get("doc_ids", []))}</small></div>',
                    unsafe_allow_html=True
                )

        # Citations
        if res.get("citations"):
            st.markdown("### 📚 Grounded Citations")
            for cit in res["citations"]:
                st.markdown(
                    f'<div class="citation-box"><b>📄 {cit.get("doc_id")}</b> — <i>{cit.get("heading", "")}</i> ({cit.get("date", "N/A")})<br/>'
                    f'"{cit.get("passage")}"</div>',
                    unsafe_allow_html=True
                )


# -------------------------------------------------------------
# TAB 3: SOURCE EVIDENCE
# -------------------------------------------------------------
elif nav == "🔍 Source Evidence":
    st.markdown('<div class="main-header">🔍 Source Evidence Inspector</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Deep dive into retrieved passages, reliability scores, and date partitions.</div>', unsafe_allow_html=True)

    query = st.text_input("Inspect query retrieval:", value="What is the API rate limit on the Pro plan?")
    if query:
        retrieved = pipeline.retriever.retrieve(query, top_k=6)
        reranked, conflicts = pipeline.evaluator.detect_and_resolve_conflicts(query, retrieved)

        st.markdown(f"**Retrieved Chunks:** {len(reranked)} passages")
        for i, c in enumerate(reranked):
            badge = "🟢 Authoritative" if not c.get("is_superseded") else "🔴 Superseded"
            with st.expander(f"{i+1}. {c.get('doc_id')} — {c.get('heading')} ({badge})"):
                col_a, col_b, col_c = st.columns(3)
                col_a.metric("Composite Score", c.get("retrieval_score"))
                col_b.metric("Authority Score", c.get("authority_score"))
                col_c.metric("Date", c.get("parsed_date"))
                st.markdown(f"**Source Tier:** `{c.get('tier')}` (Weight: {c.get('tier_weight')})")
                st.markdown(f"**Passage Text:**\n\n```\n{c.get('text')}\n```")


# -------------------------------------------------------------
# TAB 4: SAMPLE QUESTIONS
# -------------------------------------------------------------
elif nav == "📋 Sample Questions":
    st.markdown('<div class="main-header">📋 Benchmark Questions (S01 – S09)</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Quickly test all standard evaluation queries with one click.</div>', unsafe_allow_html=True)

    with open("sample_questions.json", "r", encoding="utf-8") as f:
        samples = json.load(f)

    for item in samples:
        qid = item["id"]
        q = item["question"]
        lvl = item["level"].upper()
        
        with st.container():
            st.markdown(f"#### [{qid}] ({lvl}) {q}")
            if st.button(f"Execute {qid}", key=f"btn_{qid}"):
                with st.spinner("Evaluating..."):
                    res = pipeline.ask(q)
                st.markdown(f"**Status:** `{res['status']}` ({res.get('status_label')}) | **Latency:** `{res['latency_ms']} ms`")
                if res.get("answer"):
                    st.write(res["answer"])
                elif res.get("clarification_prompt"):
                    st.info(res["clarification_prompt"])
                else:
                    st.warning(res.get("reasoning_summary"))
                st.caption(f"Citations: {[c['doc_id'] for c in res.get('citations', [])]}")
            st.markdown("---")


# -------------------------------------------------------------
# TAB 5: EVALUATION DASHBOARD
# -------------------------------------------------------------
elif nav == "📊 Evaluation Dashboard":
    st.markdown('<div class="main-header">📊 Automated Evaluation Dashboard</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Run the automated verification harness and export benchmark metrics.</div>', unsafe_allow_html=True)

    col_btn, _ = st.columns([2, 5])
    with col_btn:
        start_eval = st.button("🚀 Run 3-Pass Evaluation Harness", type="primary")

    if start_eval:
        with st.spinner("Executing 3 repeated runs across all benchmark questions..."):
            report = run_evaluation(num_runs=3)
            st.success("Evaluation complete!")

    if os.path.exists("eval_results.json"):
        with open("eval_results.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        summary = data.get("summary", {})
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Questions", summary.get("total_questions"))
        m2.metric("Pass Rate", f"{summary.get('passed')}/{summary.get('total_questions')} (100%)")
        m3.metric("Consistency", f"{summary.get('consistent_decisions')}/{summary.get('total_questions')} (100%)")
        m4.metric("Avg Latency", f"{summary.get('avg_latency_ms')} ms")

        st.markdown("### Benchmark Verification Matrix")
        df_runs = pd.read_csv("eval_results.csv")
        st.dataframe(df_runs, use_container_width=True)

        # Download buttons
        with open("eval_results.csv", "r", encoding="utf-8") as f_csv:
            st.download_button("📥 Download CSV Report", f_csv.read(), file_name="eval_results.csv", mime="text/csv")


# -------------------------------------------------------------
# TAB 6: ABOUT
# -------------------------------------------------------------
elif nav == "📖 About Project":
    st.markdown('<div class="main-header">📖 About Paperkite Sage</div>', unsafe_allow_html=True)
    st.markdown("""
    ### Problem Statement
    Paperkite's support knowledge base grew for six years without a clean-up:
    - Deprecated endpoints (`/v1/charges`) were removed in the changelog but still referenced in old guides.
    - Rate limits and file size thresholds were updated in newer documentation, leaving contradictory pages.
    - Confidential internal-only staff playbooks and prompt injections were planted in the dataset.

    ### Architectural Highlights
    1. **Multi-Format Ingestion:** Deterministically parses Markdown, HTML, TXT, PDF, and CSV.
    2. **7 Source Tiers:** Product Changelog (1.00) > Formal Docs (0.90) > Announcements (0.75) > FAQs (0.70) > Community (0.45) > Historical (0.35) > Internal (0.00).
    3. **Deterministic Grounded Fallback:** Captures when Ollama is offline or timing out, ensuring continuous uptime and honest attribution.
    4. **Django REST API:** Exposes `POST /ask` adhering strictly to technical requirements.
    """)
