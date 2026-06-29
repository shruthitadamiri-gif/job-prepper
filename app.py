import streamlit as st
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools.jd_parser import parse_jd
from agents.resume_agent import run_resume_agent
from agents.prep_agent import run_prep_agent
from agents.evaluator import run_evaluator
from graph import build_graph

# ---------------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------------
st.set_page_config(
    page_title="Job Prepper",
    page_icon="🎯",
    layout="wide"
)

# ---------------------------------------------------------------
# STYLES
# ---------------------------------------------------------------
st.markdown("""
<style>
    .main { max-width: 900px; }
    .score-pass { color: #059669; font-weight: 600; }
    .score-warn { color: #d97706; font-weight: 600; }
    .score-fail { color: #dc2626; font-weight: 600; }
    .section-header { font-size: 18px; font-weight: 600; margin-bottom: 8px; }
    .eval-card { background: #f8faff; border-left: 3px solid #3b82f6;
                 padding: 12px 16px; border-radius: 0 8px 8px 0; margin-bottom: 8px; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------
# SESSION STATE — persists across reruns
# ---------------------------------------------------------------
if "stage" not in st.session_state:
    st.session_state.stage = "input"
if "result" not in st.session_state:
    st.session_state.result = None
if "approved_resume" not in st.session_state:
    st.session_state.approved_resume = None
if "approved_prep" not in st.session_state:
    st.session_state.approved_prep = None

# ---------------------------------------------------------------
# HEADER
# ---------------------------------------------------------------
st.title("🎯 Job Prepper")
st.caption("Paste a job description and get a tailored resume + interview prep — powered by an agentic AI system")
st.divider()

# ---------------------------------------------------------------
# STAGE 1: INPUT
# ---------------------------------------------------------------
if st.session_state.stage == "input":

    role = st.text_input(
        "Role you're applying to",
        placeholder="e.g. Senior AI Product Manager at Google DeepMind"
    )

    jd_text = st.text_area(
        "Paste the full job description",
        height=300,
        placeholder="Paste the complete job description here..."
    )

    col1, col2 = st.columns([1, 3])
    with col1:
        run_btn = st.button("Run Job Prepper ↗", type="primary", use_container_width=True)

    if run_btn:
        if not jd_text.strip():
            st.error("Please paste a job description first.")
        else:
            st.session_state.stage = "running"
            st.session_state.jd_text = jd_text
            st.session_state.role = role
            st.rerun()

# ---------------------------------------------------------------
# STAGE 2: RUNNING
# ---------------------------------------------------------------
elif st.session_state.stage == "running":

    st.subheader("Running your agentic job prep system...")
    st.caption("Four agents are working in sequence. This takes about 30–60 seconds.")

    progress = st.progress(0)
    status = st.empty()

    try:
        status.info("🔍 Step 1/4 — Parsing job description...")
        progress.progress(10)
        parsed_jd = parse_jd(st.session_state.jd_text)
        progress.progress(25)

        status.info("📝 Step 2/4 — Tailoring your resume...")
        resume_output = run_resume_agent(st.session_state.jd_text, parsed_jd)
        progress.progress(50)

        status.info("🎯 Step 3/4 — Building interview prep...")
        prep_output = run_prep_agent(st.session_state.jd_text, parsed_jd)
        progress.progress(75)

        status.info("⚖️ Step 4/4 — Evaluating quality...")
        eval_result = run_evaluator(
            resume_output, prep_output,
            st.session_state.jd_text, parsed_jd
        )
        progress.progress(100)

        st.session_state.result = {
            "parsed_jd": parsed_jd,
            "resume_output": resume_output,
            "prep_output": prep_output,
            "eval_result": eval_result
        }
        st.session_state.approved_resume = resume_output
        st.session_state.approved_prep = prep_output
        st.session_state.stage = "review"
        status.success("Done! Reviewing your results...")
        st.rerun()

    except Exception as e:
        st.error(f"Something went wrong: {str(e)}")
        if st.button("Start over"):
            st.session_state.stage = "input"
            st.rerun()

# ---------------------------------------------------------------
# STAGE 3: HUMAN-IN-THE-LOOP REVIEW
# ---------------------------------------------------------------
elif st.session_state.stage == "review":

    result = st.session_state.result
    parsed_jd = result["parsed_jd"]
    eval_result = result["eval_result"]

    # Header
    role = parsed_jd.get("role", "")
    company = parsed_jd.get("company", "")
    st.subheader(f"Results: {role} at {company}")

    # Eval scores bar
    with st.expander("📊 Quality scores from evaluator agent", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            score = eval_result["relevance_score"]
            color = "score-pass" if score >= 7 else "score-fail"
            st.markdown(f"**JD Relevance**")
            st.markdown(f'<span class="{color}">{score}/10</span>', unsafe_allow_html=True)
            st.caption(eval_result["feedback"]["relevance"])
        with col2:
            score = eval_result["accuracy_score"]
            color = "score-pass" if score >= 7 else "score-fail"
            st.markdown(f"**Factual Accuracy**")
            st.markdown(f'<span class="{color}">{score}/10</span>', unsafe_allow_html=True)
            st.caption(eval_result["feedback"]["accuracy"])
        with col3:
            score = eval_result["ats_score"]
            color = "score-pass" if score >= 7 else "score-fail"
            st.markdown(f"**ATS Keywords**")
            st.markdown(f'<span class="{color}">{score}/10</span>', unsafe_allow_html=True)
            st.caption(eval_result["feedback"]["ats"])

        overall = eval_result["overall_score"]
        if eval_result["passes"]:
            st.success(f"✅ Overall score: {overall}/10 — passes quality threshold")
        else:
            st.warning(f"⚠️ Overall score: {overall}/10 — below threshold, review carefully")

    st.divider()

    # Tabs for resume and prep
    tab1, tab2 = st.tabs(["📄 Tailored Resume", "🎯 Interview Prep"])

    with tab1:
        st.markdown("**Review and edit your tailored resume below. Approve when ready.**")
        edited_resume = st.text_area(
            "Tailored resume",
            value=st.session_state.approved_resume,
            height=500,
            label_visibility="collapsed"
        )
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            if st.button("✅ Approve Resume", type="primary"):
                st.session_state.approved_resume = edited_resume
                st.success("Resume approved!")
        with col2:
            if st.button("🔄 Regenerate Resume"):
                with st.spinner("Regenerating resume..."):
                    new_resume = run_resume_agent(
                        st.session_state.jd_text,
                        parsed_jd
                    )
                    st.session_state.approved_resume = new_resume
                    st.session_state.result["resume_output"] = new_resume
                st.rerun()

    with tab2:
        st.markdown("**Your interview prep guide. Edit or approve as needed.**")
        edited_prep = st.text_area(
            "Interview prep",
            value=st.session_state.approved_prep,
            height=500,
            label_visibility="collapsed"
        )
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            if st.button("✅ Approve Prep", type="primary"):
                st.session_state.approved_prep = edited_prep
                st.success("Interview prep approved!")
        with col2:
            if st.button("🔄 Regenerate Prep"):
                with st.spinner("Regenerating interview prep..."):
                    new_prep = run_prep_agent(
                        st.session_state.jd_text,
                        parsed_jd
                    )
                    st.session_state.approved_prep = new_prep
                    st.session_state.result["prep_output"] = new_prep
                st.rerun()

    st.divider()

    # Export and reset
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("📥 Download Resume", use_container_width=True):
            st.download_button(
                label="Download as .txt",
                data=st.session_state.approved_resume,
                file_name=f"resume_{company.lower().replace(' ', '_')}.txt",
                mime="text/plain"
            )
    with col2:
        if st.button("🔁 Start Over with New JD", use_container_width=True):
            for key in ["stage", "result", "approved_resume", "approved_prep", "jd_text", "role"]:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()
