import streamlit as st
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
from datetime import datetime
from tools.jd_parser import parse_jd
from agents.resume_agent import run_resume_agent
from agents.prep_agent import run_prep_agent
from agents.evaluator import run_evaluator
from agents.ats_agent import run_ats_agent
from tools.docx_export import resume_to_docx
from tools.jd_fetcher import fetch_jd_from_url
from tools.visa_check import check_visa_sponsorship
from tools.history_store import save_entry, load_history, set_applied, delete_entry
from graph import build_graph

# ---------------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------------
st.set_page_config(page_title="Job Prepper", page_icon="🎯", layout="wide")

st.markdown("""
<style>
    .main { max-width: 900px; }
    .score-pass { color: #059669; font-weight: 600; }
    .score-fail { color: #dc2626; font-weight: 600; }
    .eval-card { background: #f8faff; border-left: 3px solid #3b82f6;
                 padding: 12px 16px; border-radius: 0 8px 8px 0; margin-bottom: 8px; }
    .hist-row-applied { opacity: 0.55; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------
# SESSION STATE
# ---------------------------------------------------------------
for key, default in [
    ("stage", "input"), ("result", None),
    ("approved_resume", None), ("approved_prep", None),
    ("history_saved", False),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ---------------------------------------------------------------
# HEADER
# ---------------------------------------------------------------
st.title("🎯 Job Prepper")
st.caption("Paste a job description and get a tailored resume + interview prep — powered by an agentic AI system")
st.divider()

tab_run, tab_history = st.tabs(["🎯 Run Job Prepper", "📋 Application History"])

# ===============================================================
# TAB 1 — MAIN WORKFLOW
# ===============================================================
with tab_run:

    # -----------------------------------------------------------
    # STAGE 1: INPUT
    # -----------------------------------------------------------
    if st.session_state.stage == "input":

        col_left, col_right = st.columns([1, 1], gap="large")

        # ---- LEFT: URL input ----
        with col_left:
            st.markdown("#### 🔗 Paste a job posting URL")
            st.caption("Enter the link and click Fetch — the description will auto-populate on the right.")
            jd_url = st.text_input(
                "Job posting URL",
                placeholder="https://company.com/careers/job-id",
                label_visibility="collapsed"
            )
            fetch_btn = st.button("⬇ Fetch job description", type="primary", use_container_width=True)

            if fetch_btn:
                if not jd_url.strip():
                    st.error("Please enter a URL first.")
                else:
                    with st.spinner("Fetching the job posting..."):
                        fetch_result = fetch_jd_from_url(jd_url.strip())
                    if fetch_result["success"]:
                        st.session_state.jd_text_draft = fetch_result["jd_text"]
                        st.success(fetch_result["message"])
                        st.rerun()
                    else:
                        st.warning(fetch_result["message"])

            st.markdown(
                '<p style="color:#94a3b8;font-size:12px;margin-top:16px">'
                'Some job boards block automated fetching. If the fetch fails, '
                'copy-paste the description manually on the right.</p>',
                unsafe_allow_html=True
            )

        # ---- RIGHT: Role + Description ----
        with col_right:
            st.markdown("#### 📝 Role & job description")
            st.caption("Auto-filled from the URL above, or type / paste directly.")
            role = st.text_input(
                "Role you're applying to",
                placeholder="e.g. Senior AI Product Manager at Google DeepMind",
                label_visibility="collapsed"
            )
            jd_text = st.text_area(
                "Job description",
                height=340,
                value=st.session_state.get("jd_text_draft", ""),
                placeholder="Paste the full job description here, or fetch it from a URL on the left.",
                label_visibility="collapsed"
            )

        st.divider()
        col_run, _ = st.columns([1, 3])
        with col_run:
            run_btn = st.button("Run Job Prepper ↗", type="primary", use_container_width=True)

        if run_btn:
            if not jd_text.strip():
                st.error("Please paste a job description or fetch one from a URL first.")
            else:
                st.session_state.stage = "running"
                st.session_state.jd_text = jd_text
                st.session_state.role = role
                st.session_state.history_saved = False
                st.session_state.pop("jd_text_draft", None)
                st.rerun()

    # -----------------------------------------------------------
    # STAGE 2: RUNNING
    # -----------------------------------------------------------
    elif st.session_state.stage == "running":

        st.subheader("Running your agentic job prep system...")
        st.caption("Six steps — visa check first, then five agents. Takes about 60–90 seconds.")

        progress = st.progress(0)
        status = st.empty()

        try:
            status.info("🔍 Step 1/6 — Parsing job description...")
            progress.progress(8)
            parsed_jd = parse_jd(st.session_state.jd_text)
            progress.progress(16)

            status.info("🛂 Step 2/6 — Checking visa sponsorship eligibility...")
            company = parsed_jd.get("company", "this company")
            visa_result = check_visa_sponsorship(st.session_state.jd_text, company)
            progress.progress(24)

            _visa_msg = f"**{visa_result['headline']}**\n\n{visa_result['detail']}"
            if visa_result["color"] == "success":
                st.success(_visa_msg)
            elif visa_result["color"] == "error":
                st.error(_visa_msg)
            elif visa_result["color"] == "info":
                st.info(_visa_msg)
            else:
                st.warning(_visa_msg)

            status.info("📝 Step 3/6 — Tailoring your resume...")
            resume_output = run_resume_agent(st.session_state.jd_text, parsed_jd)
            progress.progress(42)

            status.info("🎯 Step 4/6 — Searching the web for real interview Qs + building prep guide...")
            prep_output = run_prep_agent(st.session_state.jd_text, parsed_jd)
            progress.progress(60)

            status.info("⚖️ Step 5/6 — Evaluating quality...")
            eval_result = run_evaluator(
                resume_output,
                json.dumps(prep_output) if isinstance(prep_output, dict) else prep_output,
                st.session_state.jd_text, parsed_jd
            )
            progress.progress(80)

            status.info("🧩 Step 6/6 — Checking ATS keyword coverage...")
            ats_result = run_ats_agent(resume_output, parsed_jd)
            progress.progress(100)

            st.session_state.result = {
                "parsed_jd": parsed_jd,
                "resume_output": resume_output,
                "prep_output": prep_output,
                "eval_result": eval_result,
                "visa_result": visa_result,
                "ats_result": ats_result,
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

    # -----------------------------------------------------------
    # STAGE 3: REVIEW
    # -----------------------------------------------------------
    elif st.session_state.stage == "review":

        result = st.session_state.result
        parsed_jd = result["parsed_jd"]
        eval_result = result["eval_result"]
        role = parsed_jd.get("role", "")
        company = parsed_jd.get("company", "")

        # Auto-save to history once per run
        if not st.session_state.history_saved:
            try:
                save_entry(parsed_jd, eval_result, st.session_state.approved_resume, st.session_state.jd_text)
                st.session_state.history_saved = True
            except Exception as _e:
                st.warning(f"History save failed: {_e}")

        st.subheader(f"Results: {role} at {company}")

        # Visa banner
        visa_result = result.get("visa_result", {})
        if visa_result:
            _src = " *(source: job description)*" if visa_result.get("source") == "jd" else " *(source: public H1B records)*" if visa_result.get("source") == "web" else ""
            _visa_msg = f"**{visa_result['headline']}**  \n{visa_result['detail']}{_src}"
            if visa_result["color"] == "success":
                st.success(_visa_msg)
            elif visa_result["color"] == "error":
                st.error(_visa_msg)
            elif visa_result["color"] == "info":
                st.info(_visa_msg)
            else:
                st.warning(_visa_msg)

        # Eval scores
        with st.expander("📊 Quality scores from evaluator agent", expanded=True):
            col1, col2, col3 = st.columns(3)
            with col1:
                score = eval_result["relevance_score"]
                color = "score-pass" if score >= 7 else "score-fail"
                st.markdown("**JD Relevance**")
                st.markdown(f'<span class="{color}">{score}/10</span>', unsafe_allow_html=True)
                st.caption(eval_result["feedback"]["relevance"])
            with col2:
                score = eval_result["accuracy_score"]
                color = "score-pass" if score >= 7 else "score-fail"
                st.markdown("**Factual Accuracy**")
                st.markdown(f'<span class="{color}">{score}/10</span>', unsafe_allow_html=True)
                st.caption(eval_result["feedback"]["accuracy"])
            with col3:
                score = eval_result["ats_score"]
                color = "score-pass" if score >= 7 else "score-fail"
                st.markdown("**ATS Keywords**")
                st.markdown(f'<span class="{color}">{score}/10</span>', unsafe_allow_html=True)
                st.caption(eval_result["feedback"]["ats"])

            overall = eval_result["overall_score"]
            if eval_result["passes"]:
                st.success(f"✅ Overall score: {overall}/10 — passes quality threshold")
            else:
                st.warning(f"⚠️ Overall score: {overall}/10 — below threshold, review carefully")

        # ATS gap
        ats_result = result["ats_result"]
        with st.expander("🧩 ATS keyword gap analysis", expanded=True):
            st.markdown(
                f"**Keyword coverage: {ats_result['coverage_percent']}%** "
                f"({len(ats_result['matched_keywords'])}/{ats_result['total_keywords']} JD keywords found in resume)"
            )
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("✅ **Matched keywords**")
                st.write(", ".join(ats_result["matched_keywords"]) if ats_result["matched_keywords"] else "None matched.")
            with col2:
                st.markdown("❌ **Missing keywords**")
                if ats_result["missing_keywords"]:
                    st.write(", ".join(ats_result["missing_keywords"]))
                    st.caption("Consider weaving these into the resume if truthful.")
                else:
                    st.caption("None missing — full coverage!")

        st.divider()

        # Resume + Prep tabs
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
                    st.session_state.result["ats_result"] = run_ats_agent(edited_resume, parsed_jd)
                    st.success("Resume approved!")
                    st.rerun()
            with col2:
                if st.button("🔄 Regenerate Resume"):
                    missing = result["ats_result"].get("missing_keywords", [])
                    with st.spinner(f"Regenerating resume — targeting {len(missing)} missing keyword(s)..."):
                        new_resume = run_resume_agent(
                            st.session_state.jd_text, parsed_jd,
                            missing_keywords=missing
                        )
                        st.session_state.approved_resume = new_resume
                        st.session_state.result["resume_output"] = new_resume
                        st.session_state.result["ats_result"] = run_ats_agent(new_resume, parsed_jd)
                    st.rerun()

        with tab2:
            prep = result["prep_output"]

            CATEGORY_COLORS = {
                "Behavioral":      ("#1d4ed8", "#dbeafe"),
                "Technical AI/ML": ("#6d28d9", "#ede9fe"),
                "Product Sense":   ("#065f46", "#d1fae5"),
                "Situational":     ("#92400e", "#fef3c7"),
            }

            def category_badge(cat):
                fg, bg = CATEGORY_COLORS.get(cat, ("#374151", "#f3f4f6"))
                return (f'<span style="background:{bg};color:{fg};padding:2px 10px;'
                        f'border-radius:12px;font-size:12px;font-weight:600">{cat}</span>')

            def topic_badge(topic):
                return (f'<span style="background:#f1f5f9;color:#475569;padding:2px 10px;'
                        f'border-radius:12px;font-size:12px;font-weight:500;'
                        f'border:1px solid #cbd5e1">🏷 {topic}</span>')

            st.markdown("### 📚 Preparation Topics")
            for i, t in enumerate(prep.get("prep_topics", []), 1):
                with st.expander(f"**{i}. {t['title']}**", expanded=False):
                    st.markdown(f"**Why it matters:** {t['why_it_matters']}")
                    st.markdown(f"**What to prepare:** {t['what_to_prepare']}")

            st.divider()
            st.markdown("### ❓ Interview Questions")

            for cat in ["Behavioral", "Technical AI/ML", "Product Sense", "Situational"]:
                cat_qs = [q for q in prep.get("questions", []) if q.get("category") == cat]
                if not cat_qs:
                    continue
                fg, bg = CATEGORY_COLORS.get(cat, ("#374151", "#f3f4f6"))
                st.markdown(
                    f'<div style="background:{bg};color:{fg};padding:6px 14px;'
                    f'border-radius:8px;font-weight:700;font-size:14px;'
                    f'margin:20px 0 10px 0">{cat}</div>',
                    unsafe_allow_html=True
                )
                for q in cat_qs:
                    reported_tag = ' <span style="color:#dc2626;font-size:11px;font-weight:700">● REPORTED</span>' if q.get("reported") else ""
                    with st.expander(q["question"], expanded=False):
                        st.markdown(f'{category_badge(q["category"])} &nbsp; {topic_badge(q["topic"])}{reported_tag}', unsafe_allow_html=True)
                        st.caption(f"💡 {q['hint']}")
                        st.markdown("**Answer angles:**")
                        for opt in q.get("answer_options", []):
                            st.markdown(
                                f'<div style="background:#f8faff;border-left:3px solid #3b82f6;'
                                f'padding:10px 14px;border-radius:0 6px 6px 0;margin:6px 0">'
                                f'<strong>{opt["angle"]}</strong><br>{opt["outline"]}</div>',
                                unsafe_allow_html=True
                            )

            col1, _ = st.columns([1, 3])
            with col1:
                if st.button("🔄 Regenerate Prep"):
                    with st.spinner("Searching web + regenerating prep guide..."):
                        new_prep = run_prep_agent(st.session_state.jd_text, parsed_jd)
                        st.session_state.approved_prep = new_prep
                        st.session_state.result["prep_output"] = new_prep
                    st.rerun()

        st.divider()

        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            st.download_button(
                label="📥 Download .txt",
                data=st.session_state.approved_resume,
                file_name=f"resume_{company.lower().replace(' ', '_')}.txt",
                mime="text/plain",
                use_container_width=True
            )
        with col2:
            st.download_button(
                label="📥 Download .docx",
                data=resume_to_docx(st.session_state.approved_resume),
                file_name=f"resume_{company.lower().replace(' ', '_')}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True
            )
        with col3:
            if st.button("🔁 Start Over with New JD", use_container_width=True):
                for key in ["stage", "result", "approved_resume", "approved_prep",
                            "jd_text", "role", "jd_text_draft", "history_saved"]:
                    st.session_state.pop(key, None)
                st.rerun()

# ===============================================================
# TAB 2 — APPLICATION HISTORY
# ===============================================================
with tab_history:

    st.subheader("📋 Application History")
    st.caption("Every job prep run is saved here automatically. Check the box once you've applied.")

    entries = load_history()

    if not entries:
        st.info("No history yet — run Job Prepper on a role to see it here.")
    else:
        for entry in entries:
            applied = entry.get("applied", False)
            score = entry.get("relevance_score", 0)
            score_color = "#059669" if score >= 7 else "#d97706" if score >= 5 else "#dc2626"
            date_str = entry.get("date_created", "")[:10]
            loc = entry.get("location", "") or "—"
            salary = entry.get("salary_range", "") or "Not listed"

            # Card wrapper — slightly muted if applied
            opacity = "0.6" if applied else "1.0"
            st.markdown(
                f'<div style="opacity:{opacity};border:1px solid #e2e8f0;border-radius:10px;'
                f'padding:14px 18px;margin-bottom:12px;background:{"#f8faff" if not applied else "#f1f5f9"}">',
                unsafe_allow_html=True
            )

            col_main, col_score, col_action = st.columns([4, 1, 1])

            with col_main:
                applied_badge = ' <span style="background:#d1fae5;color:#065f46;padding:1px 8px;border-radius:10px;font-size:11px;font-weight:600">✓ Applied</span>' if applied else ''
                st.markdown(
                    f'**{entry["company"]}** — {entry["role"]}{applied_badge}',
                    unsafe_allow_html=True
                )
                st.caption(f"📅 {date_str} &nbsp;|&nbsp; 📍 {loc} &nbsp;|&nbsp; 💰 {salary}")

            with col_score:
                st.markdown(
                    f'<div style="text-align:center;padding-top:4px">'
                    f'<span style="font-size:20px;font-weight:700;color:{score_color}">{score}</span>'
                    f'<span style="font-size:11px;color:#94a3b8">/10</span><br>'
                    f'<span style="font-size:10px;color:#94a3b8">relevance</span></div>',
                    unsafe_allow_html=True
                )

            with col_action:
                new_applied = st.checkbox(
                    "Applied",
                    value=applied,
                    key=f"applied_{entry['id']}"
                )
                if new_applied != applied:
                    set_applied(entry["id"], new_applied)
                    st.rerun()

            # Resume download + delete (always available)
            exp_label = f"📄 View / Download Resume — {entry['company']}"
            with st.expander(exp_label, expanded=False):
                st.text_area(
                    "Resume",
                    value=entry.get("resume_output", ""),
                    height=300,
                    label_visibility="collapsed",
                    disabled=True,
                    key=f"resume_view_{entry['id']}"
                )
                dl_col, del_col, _ = st.columns([1, 1, 3])
                with dl_col:
                    fname = f"resume_{entry['company'].lower().replace(' ','_')}.docx"
                    st.download_button(
                        "📥 Download .docx",
                        data=resume_to_docx(entry.get("resume_output", "")),
                        file_name=fname,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True,
                        key=f"dl_{entry['id']}"
                    )
                with del_col:
                    if st.button("🗑 Delete", key=f"del_{entry['id']}", use_container_width=True):
                        delete_entry(entry["id"])
                        st.rerun()

            st.markdown("</div>", unsafe_allow_html=True)
