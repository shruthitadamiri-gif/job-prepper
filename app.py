import streamlit as st
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
from datetime import datetime
from agents.resume_agent import run_resume_agent
from agents.prep_agent import run_prep_agent
from agents.ats_agent import run_ats_agent
from tools.docx_export import resume_to_docx
from tools.jd_fetcher import fetch_jd_from_url
from tools.opportunity_store import (
    create_opportunity, list_opportunities, update_stage, update_fields,
    delete_opportunity,
)
from agents.title_discovery_agent import discover_titles
from tools.job_search import search_all_titles, job_key as _job_key
from tools.batch_runner import run_batch, run_prep_for_result
from graph import build_graph, make_initial_state

# ---------------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------------
st.set_page_config(page_title="Job Prepper", page_icon="🎯", layout="wide")

# ---------------------------------------------------------------
# PASSWORD GATE
# ---------------------------------------------------------------
def _get_app_password() -> str:
    try:
        return st.secrets["APP_PASSWORD"]
    except Exception:
        return os.getenv("APP_PASSWORD", "")

_expected_pw = _get_app_password()
if not _expected_pw:
    st.error("APP_PASSWORD is not configured. Set it in Streamlit secrets or your .env file.")
    st.stop()

if not st.session_state.get("_authenticated"):
    pw = st.text_input("Enter password to access Job Prepper", type="password")
    if pw == _expected_pw:
        st.session_state["_authenticated"] = True
        st.rerun()
    elif pw:
        st.error("Incorrect password.")
    st.stop()

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
    ("opportunity_id", None), ("history_saved", False), ("page", "search"),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ---------------------------------------------------------------
# HEADER + NAV
# ---------------------------------------------------------------
st.title("🎯 Job Prepper")
st.caption("Find roles, tailor your resume, and prep for interviews — powered by an agentic AI system")

nav_cols = st.columns([1, 1, 1, 4])
pages = [("🔍 Job Search", "search"), ("🎯 Run Job Prepper", "run"), ("📋 Pipeline", "pipeline")]
for col, (label, key) in zip(nav_cols, pages):
    with col:
        active = st.session_state.page == key
        if st.button(label, use_container_width=True,
                     type="primary" if active else "secondary"):
            st.session_state.page = key
            st.rerun()

st.divider()
page = st.session_state.page

# ===============================================================
# PAGE: RUN JOB PREPPER
# ===============================================================
if page == "run":

    # -----------------------------------------------------------
    # BATCH MODE: jobs passed from job search
    # -----------------------------------------------------------
    if st.session_state.get("js_pending_jobs"):
        pending = st.session_state.js_pending_jobs
        st.subheader(f"Running Job Prepper for {len(pending)} selected role{'s' if len(pending) > 1 else ''}...")
        st.caption("Running in parallel — takes about 45 seconds.")

        with st.spinner("Tailoring resumes + scoring ATS in parallel..."):
            batch_results = run_batch(pending)

        for r in batch_results:
            if "error" not in r:
                try:
                    pjd = r["parsed_jd"] or {}
                    job = r.get("job", {})
                    create_opportunity(
                        title=pjd.get("role", job.get("title", "")),
                        company=pjd.get("company", job.get("company", "")),
                        location=pjd.get("location", job.get("location", "")),
                        url=job.get("url", ""),
                        jd_snapshot=r.get("jd_text", ""),
                        source="search",
                        stage="tailored",
                        eval_result=r.get("eval_result"),
                        ats_result=r.get("ats_result"),
                    )
                except Exception:
                    pass

        st.session_state.js_batch_results = batch_results
        st.session_state.js_pending_jobs = None
        st.rerun()

    # -----------------------------------------------------------
    # BATCH RESULTS VIEW
    # -----------------------------------------------------------
    if st.session_state.get("js_batch_results"):
        batch_results = st.session_state.js_batch_results
        st.subheader("Job Prepper Results")
        st.caption("Click 'Open full results' to access resume editing, ATS gap, regenerate, interview prep and all other tools.")

        for i, r in enumerate(batch_results):
            job = r["job"]
            if "error" in r:
                st.error(f"**{job['title']} at {job['company']}** — failed: {r['error']}")
                continue

            ats_pct = r["ats_result"]["coverage_percent"]
            rel_score = r["eval_result"]["overall_score"]
            ats_color = "#059669" if ats_pct >= 70 else "#d97706" if ats_pct >= 50 else "#dc2626"
            rel_color = "#059669" if rel_score >= 7 else "#d97706" if rel_score >= 5 else "#dc2626"

            col_info, col_ats, col_rel, col_open = st.columns([4, 1, 1, 1])
            with col_info:
                st.markdown(f"**{job['title']}**")
                st.caption(f"{job['company']} &nbsp;·&nbsp; {job.get('location','')}")
            with col_ats:
                st.markdown(f'<div style="text-align:center"><span style="font-size:20px;font-weight:700;color:{ats_color}">{ats_pct}%</span><br><span style="font-size:11px;color:#94a3b8">ATS</span></div>', unsafe_allow_html=True)
            with col_rel:
                st.markdown(f'<div style="text-align:center"><span style="font-size:20px;font-weight:700;color:{rel_color}">{rel_score}/10</span><br><span style="font-size:11px;color:#94a3b8">relevance</span></div>', unsafe_allow_html=True)
            with col_open:
                if st.button("Open →", key=f"open_{i}", use_container_width=True):
                    # Load this result into the full review stage
                    st.session_state.result = {
                        "parsed_jd": r["parsed_jd"],
                        "resume_output": r["resume_output"],
                        "prep_output": r.get("prep_output"),
                        "eval_result": r["eval_result"],
                        "visa_result": {},
                        "ats_result": r["ats_result"],
                    }
                    st.session_state.approved_resume = r["resume_output"]
                    st.session_state.approved_prep = r.get("prep_output")
                    st.session_state.original_ats_result = r["ats_result"]
                    st.session_state.jd_text = r["jd_text"]
                    st.session_state.history_saved = True
                    st.session_state.stage = "review"
                    st.session_state.js_batch_results = None
                    st.rerun()

            st.divider()

        if st.button("← Back to Job Search"):
            st.session_state.js_batch_results = None
            st.session_state.page = "search"
            st.rerun()

    # -----------------------------------------------------------
    # STAGE 1: INPUT (single JD flow)
    # -----------------------------------------------------------
    elif st.session_state.stage == "input" and not st.session_state.get("js_batch_results"):

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
        st.caption("Visa check + resume tailoring + ATS analysis + quality evaluation. Takes about 60–90 seconds.")

        # Progress mapped to node completions from the LangGraph stream
        NODE_PROGRESS = {
            "parse_jd":        (15, "🔍 Parsing job description..."),
            "visa_check":      (30, "🛂 Checking visa sponsorship eligibility..."),
            "resume_agent":    (55, "📝 Tailoring your resume..."),
            "ats_agent":       (75, "🧩 Checking ATS keyword coverage..."),
            "evaluator":       (90, "⚖️ Evaluating quality..."),
            "increment_retry": (55, "🔄 Quality check failed — regenerating resume with ATS feedback..."),
            "package_output":  (100, "✅ Packaging results..."),
        }

        progress = st.progress(0)
        status = st.empty()
        visa_placeholder = st.empty()

        try:
            graph = build_graph()
            final_state = None

            for event in graph.stream(make_initial_state(st.session_state.jd_text)):
                for node_name, node_state in event.items():
                    pct, msg = NODE_PROGRESS.get(node_name, (50, f"Running {node_name}..."))
                    progress.progress(pct)
                    status.info(msg)
                    final_state = node_state

                    # Show visa banner as soon as it's ready
                    if node_name == "visa_check":
                        visa_result = node_state.get("visa_result", {})
                        if visa_result:
                            _msg = f"**{visa_result['headline']}**\n\n{visa_result['detail']}"
                            color = visa_result.get("color", "warning")
                            if color == "success":
                                visa_placeholder.success(_msg)
                            elif color == "error":
                                visa_placeholder.error(_msg)
                            elif color == "info":
                                visa_placeholder.info(_msg)
                            else:
                                visa_placeholder.warning(_msg)

            st.session_state.result = {
                "parsed_jd": final_state["parsed_jd"],
                "resume_output": final_state["resume_output"],
                "prep_output": None,
                "eval_result": final_state["eval_result"],
                "visa_result": final_state["visa_result"],
                "ats_result": final_state["ats_result"],
            }
            st.session_state.approved_resume = final_state["resume_output"]
            st.session_state.approved_prep = None
            st.session_state.original_ats_result = final_state["ats_result"]
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

        # Auto-save to opportunities once per run
        if not st.session_state.history_saved:
            try:
                opp_id = create_opportunity(
                    title=parsed_jd.get("role", ""),
                    company=parsed_jd.get("company", ""),
                    location=parsed_jd.get("location", ""),
                    jd_snapshot=st.session_state.jd_text,
                    source="manual",
                    stage="tailored",
                    eval_result=eval_result,
                    ats_result=result.get("ats_result"),
                )
                st.session_state.opportunity_id = opp_id
                st.session_state.history_saved = True
            except Exception as _e:
                st.warning(f"Save failed: {_e}")

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
        original_ats = st.session_state.get("original_ats_result", ats_result)
        current_pct = ats_result["coverage_percent"]
        original_pct = original_ats["coverage_percent"]
        improved = current_pct > original_pct

        with st.expander("🧩 ATS keyword gap analysis", expanded=True):
            col_cov, col_delta = st.columns([2, 1])
            with col_cov:
                st.markdown(
                    f"**Keyword coverage: {current_pct}%** "
                    f"({len(ats_result['matched_keywords'])}/{ats_result['total_keywords']} JD keywords found in resume)"
                )
            with col_delta:
                if current_pct != original_pct:
                    delta = current_pct - original_pct
                    arrow = "▲" if delta > 0 else "▼"
                    color = "#059669" if delta > 0 else "#dc2626"
                    st.markdown(
                        f'<div style="text-align:right;padding-top:4px">'
                        f'<span style="font-size:13px;font-weight:700;color:{color}">'
                        f'{arrow} {abs(delta)}% vs original</span></div>',
                        unsafe_allow_html=True
                    )

            if improved:
                st.success(f"✅ Resume improved from {original_pct}% → {current_pct}% ATS coverage after your edits.")

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

        # Unsupported claims warning (factual accuracy gate)
        unsupported = eval_result.get("unsupported_claims", [])
        if unsupported:
            claims_list = "\n".join(f"- {c}" for c in unsupported)
            st.error(
                f"⚠️ **Factual accuracy issue — {len(unsupported)} unsupported claim(s) detected**\n\n"
                f"The following claims in the tailored resume could not be traced to your source resume. "
                f"Review and remove or correct before submitting:\n\n{claims_list}"
            )

        st.divider()

        # Resume + Prep tabs
        tab1, tab2 = st.tabs(["📄 Tailored Resume", "🎯 Interview Prep"])

        with tab1:
            st.markdown("**Review and edit your tailored resume below. Approve when ready.**")
            evidence_sources = result.get("evidence_sources") or []
            if evidence_sources:
                st.caption("Career corpus evidence used: " + ", ".join(evidence_sources))
            edited_resume = st.text_area(
                "Tailored resume",
                value=st.session_state.approved_resume,
                height=500,
                label_visibility="collapsed"
            )
            col1, col2, col3 = st.columns([1, 1, 2])
            with col1:
                if st.button("✅ Approve & Re-score ATS", type="primary"):
                    st.session_state.approved_resume = edited_resume
                    st.session_state.result["ats_result"] = run_ats_agent(edited_resume, parsed_jd)
                    st.rerun()
            with col2:
                if st.button("🔄 Regenerate Resume"):
                    missing = result["ats_result"].get("missing_keywords", [])
                    with st.spinner(f"Regenerating resume — targeting {len(missing)} missing keyword(s)..."):
                        new_resume = run_resume_agent(
                            st.session_state.jd_text, parsed_jd,
                            missing_keywords=missing,
                            current_resume=st.session_state.approved_resume,
                        )
                        st.session_state.approved_resume = new_resume
                        st.session_state.result["resume_output"] = new_resume
                        st.session_state.result["ats_result"] = run_ats_agent(new_resume, parsed_jd)
                    st.rerun()

        with tab2:
            prep = result.get("prep_output")

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

            if not prep:
                st.markdown("### 🎯 Interview Prep Guide")
                st.info("Interview prep is generated on demand — it searches the web for real questions and takes ~30 seconds.")
                if st.button("🚀 Run Interview Prep", type="primary"):
                    with st.spinner("Searching the web for real interview Qs + building prep guide (~30s)..."):
                        new_prep = run_prep_agent(st.session_state.jd_text, parsed_jd)
                        st.session_state.approved_prep = new_prep
                        st.session_state.result["prep_output"] = new_prep
                    st.rerun()
            else:
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

        col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
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
            opp_id = st.session_state.get("opportunity_id")
            if opp_id:
                if st.button("✅ Mark as Applied", use_container_width=True, type="primary"):
                    try:
                        update_stage(opp_id, "applied")
                        update_fields(opp_id, {"resume_version": st.session_state.approved_resume})
                        st.success("Marked as applied — resume version saved.")
                    except Exception as _e:
                        st.warning(f"Could not update stage: {_e}")
        with col4:
            if st.button("🔁 Start Over with New JD", use_container_width=True):
                for key in ["stage", "result", "approved_resume", "approved_prep",
                            "jd_text", "role", "jd_text_draft", "history_saved", "opportunity_id"]:
                    st.session_state.pop(key, None)
                st.rerun()

# ===============================================================
# PAGE: PIPELINE
# ===============================================================
if page == "pipeline":
    from datetime import timezone as _tz

    st.subheader("📋 Application Pipeline")

    all_opps = list_opportunities()

    # ── Stage summary strip ──────────────────────────────────────
    ACTIVE_STAGES = ["discovered", "screened_in", "tailored", "applied", "responded", "interviewing"]
    stage_counts = {s: 0 for s in ACTIVE_STAGES}
    for o in all_opps:
        s = o.get("stage", "")
        if s in stage_counts:
            stage_counts[s] += 1

    metric_cols = st.columns(len(ACTIVE_STAGES))
    for col, stage in zip(metric_cols, ACTIVE_STAGES):
        with col:
            st.metric(stage.replace("_", " ").title(), stage_counts[stage])

    st.divider()

    # ── Nudges ───────────────────────────────────────────────────
    now_utc = datetime.now(_tz.utc)
    nudges = []
    for o in all_opps:
        if o.get("stage") != "applied":
            continue
        updated = o.get("stage_updated_at", "")
        try:
            updated_dt = datetime.fromisoformat(updated)
            if updated_dt.tzinfo is None:
                updated_dt = updated_dt.replace(tzinfo=_tz.utc)
            days_in = (now_utc - updated_dt).days
            if days_in >= 14:
                nudges.append((o, days_in))
        except Exception:
            pass

    if nudges:
        st.markdown("#### ⏰ Follow-up nudges")
        for o, days_in in nudges:
            nc1, nc2, nc3 = st.columns([4, 1, 1])
            with nc1:
                st.warning(
                    f"**{o.get('company','')} — {o.get('title','')}**: "
                    f"No response in {days_in}d — follow up or mark ghosted."
                )
            with nc2:
                if st.button("Mark ghosted", key=f"ghost_{o['id']}"):
                    update_stage(o["id"], "ghosted")
                    st.rerun()
            with nc3:
                if st.button("Draft follow-up", key=f"followup_{o['id']}"):
                    update_fields(o["id"], {"notes": f"[Follow-up drafted {now_utc.date()}]"})
                    st.info("Follow-up drafting coming in a future update.")
        st.divider()

    # ── Opportunities list ────────────────────────────────────────
    STAGE_ORDER = ["interviewing", "responded", "applied", "tailored",
                   "screened_in", "discovered", "offer",
                   "screened_out", "rejected", "ghosted", "withdrawn"]

    def _stage_sort_key(o):
        s = o.get("stage", "")
        try:
            return (STAGE_ORDER.index(s), o.get("stage_updated_at", ""))
        except ValueError:
            return (99, o.get("stage_updated_at", ""))

    sorted_opps = sorted(all_opps, key=_stage_sort_key)

    if not sorted_opps:
        st.info("No opportunities yet — run Job Prepper on a role to see it here.")
    else:
        ALL_STAGES = ["discovered", "screened_in", "screened_out", "tailored",
                      "applied", "responded", "interviewing", "offer",
                      "rejected", "ghosted", "withdrawn"]

        for o in sorted_opps:
            opp_id = o["id"]
            stage = o.get("stage", "tailored")
            title = o.get("title", "Unknown role")
            company = o.get("company", "Unknown company")
            updated = o.get("stage_updated_at", "")[:10]

            try:
                updated_dt = datetime.fromisoformat(o.get("stage_updated_at", ""))
                if updated_dt.tzinfo is None:
                    updated_dt = updated_dt.replace(tzinfo=_tz.utc)
                days_in = (now_utc - updated_dt).days
                days_label = f"{days_in}d in {stage.replace('_',' ')}"
            except Exception:
                days_label = stage.replace("_", " ")

            col_info, col_stage, col_del = st.columns([4, 2, 1])
            with col_info:
                st.markdown(f"**{company}** — {title}")
                st.caption(f"📅 {updated} &nbsp;|&nbsp; {days_label}")
            with col_stage:
                new_stage = st.selectbox(
                    "Stage",
                    options=ALL_STAGES,
                    index=ALL_STAGES.index(stage) if stage in ALL_STAGES else 0,
                    key=f"stage_sel_{opp_id}",
                    label_visibility="collapsed",
                )
                if new_stage != stage:
                    update_stage(opp_id, new_stage)
                    st.rerun()
            with col_del:
                if st.button("🗑", key=f"del_{opp_id}", use_container_width=True):
                    delete_opportunity(opp_id)
                    st.rerun()

            resume_ver = o.get("resume_version") or o.get("resume_output")
            if resume_ver:
                with st.expander(f"📄 Resume — {company}", expanded=False):
                    st.text_area(
                        "Resume",
                        value=resume_ver,
                        height=250,
                        label_visibility="collapsed",
                        disabled=True,
                        key=f"resume_view_{opp_id}",
                    )
                    dl_col, _ = st.columns([1, 3])
                    with dl_col:
                        fname = f"resume_{company.lower().replace(' ','_')}.docx"
                        st.download_button(
                            "📥 Download .docx",
                            data=resume_to_docx(resume_ver),
                            file_name=fname,
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            use_container_width=True,
                            key=f"dl_{opp_id}",
                        )

            st.divider()

# ===============================================================
# PAGE: JOB SEARCH
# ===============================================================
if page == "search":

    st.subheader("🔍 Job Search")

    has_serpapi = bool(os.getenv("SERPAPI_KEY", "").strip())
    if not has_serpapi:
        st.warning("Add `SERPAPI_KEY` to your Streamlit secrets to enable job search.")

    # ── STEP 1: Search controls ──────────────────────────────────
    st.markdown("#### Step 1 — Search for roles")
    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    with c1:
        st.caption("📍 Location")
        location = st.text_input("loc", value="Boston, MA", label_visibility="collapsed",
                                  placeholder="e.g. Boston, MA or Remote")
    with c2:
        st.caption("📅 Posted within")
        days_back = st.selectbox("days", [7, 14, 30], index=2,
                                  format_func=lambda d: f"{d} days",
                                  label_visibility="collapsed")
    with c3:
        st.caption("🔗 Source")
        source_filter = st.selectbox("src", ["All", "LinkedIn", "Indeed"],
                                      label_visibility="collapsed")
    with c4:
        st.caption(" ")
        search_btn = st.button("🔍 Search", type="primary", use_container_width=True,
                                disabled=not has_serpapi)

    custom_title = st.text_input(
        "➕ Add your own title",
        placeholder="e.g. AI Solutions Architect (appended to AI-discovered titles)",
    )

    if search_btn:
        with st.spinner("Discovering titles from your resume..."):
            titles_data = discover_titles()
        all_titles = (
            [t["title"] for t in titles_data["direct_fit"]] +
            [t["title"] for t in titles_data["worth_exploring"]]
        )
        if custom_title.strip():
            all_titles.append(custom_title.strip())

        with st.spinner(f"Searching {len(all_titles)} titles on Google Jobs (LinkedIn, Indeed + more)..."):
            raw_results = search_all_titles(all_titles, location=location, days_back=days_back)

        all_jobs_flat = []
        for title, jobs_for_title in raw_results.items():
            for job in jobs_for_title:
                job["searched_title"] = title
            all_jobs_flat.extend(jobs_for_title)

        # Sort globally by title_match so highest-confidence results surface first
        all_jobs_flat.sort(key=lambda j: j.get("title_match", 0), reverse=True)

        st.session_state.js_jobs = all_jobs_flat
        st.session_state.js_titles_meta = titles_data
        st.session_state.js_source_filter = source_filter
        st.session_state.js_selected = set()   # stores stable job_key strings
        st.session_state.js_batch_results = None
        st.rerun()

    # ── STEP 2: Job cards with checkboxes ────────────────────────
    if st.session_state.get("js_jobs") is not None:
        all_jobs = st.session_state.js_jobs
        active_filter = st.session_state.get("js_source_filter", "All")
        jobs = [j for j in all_jobs if active_filter == "All" or active_filter.lower() in j.get("via", "").lower()]

        st.divider()
        st.markdown("#### Step 2 — Select roles to run Job Prepper on")
        st.caption(f"{len(jobs)} jobs found — sorted by title match score, check the ones you want to analyse")

        if not jobs:
            st.info("No jobs found. Try a wider date range or 'All' sources.")
        else:
            # Selection keyed by stable job identity, not integer index —
            # so changing the source filter doesn't remap checked boxes to wrong jobs
            selected: set = st.session_state.get("js_selected", set())

            for i, job in enumerate(jobs):
                jk = _job_key(job)
                remote_badge = "🌐 Remote &nbsp;" if job.get("is_remote") else ""
                via = (
                    f' <span style="background:#ede9fe;color:#6d28d9;padding:1px 7px;'
                    f'border-radius:8px;font-size:11px">{job["via"]}</span>'
                    if job.get("via") else ""
                )
                tm = job.get("title_match", 0)
                tm_color = "#059669" if tm >= 75 else "#d97706" if tm >= 50 else "#dc2626"
                tm_badge = (
                    f'<span style="background:#f1f5f9;color:{tm_color};padding:1px 7px;'
                    f'border-radius:8px;font-size:11px;font-weight:700">'
                    f'match {tm}%</span>'
                )

                col_chk, col_info = st.columns([0.5, 9])
                with col_chk:
                    checked = st.checkbox("", key=f"sel_{i}", value=(jk in selected))
                    if checked:
                        selected.add(jk)
                    else:
                        selected.discard(jk)
                with col_info:
                    title_html = (
                        f'<a href="{job["url"]}" target="_blank" style="font-size:15px;'
                        f'font-weight:700;color:#1e293b;text-decoration:none">'
                        f'{job["title"]} ↗</a>'
                        if job.get("url") else
                        f'<strong style="font-size:15px">{job["title"]}</strong>'
                    )
                    st.markdown(
                        f'<div style="border:1px solid #e2e8f0;border-radius:8px;'
                        f'padding:10px 14px;background:#fafbff;margin-bottom:4px">'
                        f'{title_html} {tm_badge}{via}<br>'
                        f'<span style="color:#475569;font-size:13px">{job["company"]}</span>'
                        f' <span style="color:#cbd5e1">·</span> '
                        f'<span style="color:#94a3b8;font-size:12px">'
                        f'{remote_badge}📍{job["location"] or "—"} &nbsp;·&nbsp; 📅{job["date_posted"]}'
                        f'</span></div>',
                        unsafe_allow_html=True
                    )
                    if job.get("description_snippet"):
                        with st.expander("Preview description", expanded=False):
                            st.caption(job["description_snippet"])

            st.session_state.js_selected = selected

            if selected:
                st.divider()
                run_batch_btn = st.button(
                    f"⚡ Run Job Prepper for {len(selected)} selected role{'s' if len(selected) > 1 else ''} →",
                    type="primary"
                )
                if run_batch_btn:
                    st.session_state.js_pending_jobs = [j for j in jobs if _job_key(j) in selected]
                    st.session_state.page = "run"
                    st.rerun()

    # ── STEP 3: Batch results + interview prep selection ─────────
    if st.session_state.get("js_batch_results"):
        batch_results = st.session_state.js_batch_results

        st.divider()
        st.markdown("#### Step 3 — Results")
        st.caption("Scores are based on your tailored resume vs each role. Select roles for interview prep below.")

        prep_selected = set()

        for i, r in enumerate(batch_results):
            job = r["job"]

            if "error" in r:
                st.error(f"**{job['title']} at {job['company']}** — failed: {r['error']}")
                continue

            ats = r["ats_result"]
            ev = r["eval_result"]
            ats_pct = ats["coverage_percent"]
            rel_score = ev["overall_score"]
            ats_color = "#059669" if ats_pct >= 70 else "#d97706" if ats_pct >= 50 else "#dc2626"
            rel_color = "#059669" if rel_score >= 7 else "#d97706" if rel_score >= 5 else "#dc2626"

            col_info, col_ats, col_rel, col_prep = st.columns([4, 1, 1, 1])
            with col_info:
                st.markdown(f"**{job['title']}**")
                st.caption(f"{job['company']} &nbsp;·&nbsp; {job.get('location','')}")
            with col_ats:
                st.markdown(f'<div style="text-align:center"><span style="font-size:20px;font-weight:700;color:{ats_color}">{ats_pct}%</span><br><span style="font-size:11px;color:#94a3b8">ATS</span></div>', unsafe_allow_html=True)
            with col_rel:
                st.markdown(f'<div style="text-align:center"><span style="font-size:20px;font-weight:700;color:{rel_color}">{rel_score}/10</span><br><span style="font-size:11px;color:#94a3b8">relevance</span></div>', unsafe_allow_html=True)
            with col_prep:
                want_prep = st.checkbox("Add prep", key=f"prep_{i}")
                if want_prep:
                    prep_selected.add(i)

            with st.expander("📄 View tailored resume & download", expanded=False):
                st.text_area("Resume", value=r["resume_output"], height=250,
                             disabled=True, key=f"br_resume_{i}", label_visibility="collapsed")
                dl1, dl2 = st.columns(2)
                fname = f"resume_{job['company'].lower().replace(' ','_')}.docx"
                with dl1:
                    st.download_button("📥 .txt", data=r["resume_output"],
                                       file_name=fname.replace(".docx", ".txt"),
                                       mime="text/plain", key=f"br_txt_{i}",
                                       use_container_width=True)
                with dl2:
                    st.download_button("📥 .docx", data=resume_to_docx(r["resume_output"]),
                                       file_name=fname, mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                       key=f"br_docx_{i}", use_container_width=True)
            st.divider()

        # ── STEP 4: Interview prep ────────────────────────────────
        if prep_selected:
            st.markdown("#### Step 4 — Interview Prep")
            run_prep_btn = st.button(
                f"🎯 Run Interview Prep for {len(prep_selected)} selected role{'s' if len(prep_selected) > 1 else ''}",
                type="primary"
            )
            if run_prep_btn:
                for idx in sorted(prep_selected):
                    r = batch_results[idx]
                    with st.spinner(f"Building prep guide for {r['job']['title']} at {r['job']['company']}..."):
                        updated = run_prep_for_result(r)
                        st.session_state.js_batch_results[idx] = updated
                st.rerun()

        # Show any prep that's already been generated
        for i, r in enumerate(batch_results):
            if r.get("prep_output"):
                job = r["job"]
                st.markdown(f"### 🎯 Interview Prep — {job['title']} at {job['company']}")
                prep = r["prep_output"]
                for t in prep.get("prep_topics", []):
                    with st.expander(f"**{t['title']}**", expanded=False):
                        st.markdown(f"**Why it matters:** {t['why_it_matters']}")
                        st.markdown(f"**What to prepare:** {t['what_to_prepare']}")
                for q in prep.get("questions", []):
                    with st.expander(q["question"], expanded=False):
                        st.caption(f"💡 {q['hint']}")
                        for opt in q.get("answer_options", []):
                            st.markdown(
                                f'<div style="background:#f8faff;border-left:3px solid #3b82f6;'
                                f'padding:10px 14px;border-radius:0 6px 6px 0;margin:6px 0">'
                                f'<strong>{opt["angle"]}</strong><br>{opt["outline"]}</div>',
                                unsafe_allow_html=True
                            )
                st.divider()

        # ── Titles used ───────────────────────────────────────────
        with st.expander("🔎 Titles searched by AI", expanded=False):
            titles_meta = st.session_state.get("js_titles_meta", {})
            cd, ce = st.columns(2)
            with cd:
                st.markdown("**Direct fit**")
                for t in titles_meta.get("direct_fit", []):
                    st.markdown(f'<span style="background:#dbeafe;color:#1d4ed8;padding:2px 10px;border-radius:10px;font-size:12px;font-weight:600;margin:2px;display:inline-block">{t["title"]}</span>', unsafe_allow_html=True)
                    st.caption(t["rationale"])
            with ce:
                st.markdown("**Worth exploring**")
                for t in titles_meta.get("worth_exploring", []):
                    st.markdown(f'<span style="background:#ede9fe;color:#6d28d9;padding:2px 10px;border-radius:10px;font-size:12px;font-weight:600;margin:2px;display:inline-block">{t["title"]}</span>', unsafe_allow_html=True)
                    st.caption(t["rationale"])
