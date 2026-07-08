import os
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv
from tools.jd_parser import parse_jd
from agents.resume_agent import run_resume_agent
from agents.evaluator import run_evaluator
from agents.ats_agent import run_ats_agent
from tools.visa_check import check_visa_sponsorship

load_dotenv()

# ---------------------------------------------------------------
# Pipeline topology (prep runs on demand in the UI, not here):
#
#   parse_jd → visa_check → resume_agent → ats_agent → evaluator
#                               ↑                           ↓
#                       increment_retry           should_retry()
#                               ↑                  /          \
#                               └──── "retry" ────┘   "pass"
#                                                          ↓
#                                                    package_output → END
#
# Retry loop (max 2 retries): resume → ats → evaluator.
# Each retry passes missing_keywords (from latest ats_result) and the
# previous resume_output to run_resume_agent so improvements cumulate.
# increment_retry bumps retry_count BEFORE re-entering resume_agent,
# fixing the original bug where retry_count was never incremented.
# ---------------------------------------------------------------

class JobPrepState(TypedDict):
    jd_text: str
    parsed_jd: Optional[dict]
    visa_result: Optional[dict]
    resume_output: Optional[str]
    eval_result: Optional[dict]
    ats_result: Optional[dict]
    retry_count: int
    final_output: Optional[dict]


def make_initial_state(jd_text: str) -> JobPrepState:
    return {
        "jd_text": jd_text,
        "parsed_jd": None,
        "visa_result": None,
        "resume_output": None,
        "eval_result": None,
        "ats_result": None,
        "retry_count": 0,
        "final_output": None,
    }


# ---------------------------------------------------------------
# NODES
# ---------------------------------------------------------------

def parse_jd_node(state: JobPrepState) -> JobPrepState:
    print("Parsing job description...")
    parsed = parse_jd(state["jd_text"])
    return {**state, "parsed_jd": parsed}


def visa_check_node(state: JobPrepState) -> JobPrepState:
    print("Checking visa sponsorship...")
    try:
        company = (state["parsed_jd"] or {}).get("company", "")
        visa_result = check_visa_sponsorship(state["jd_text"], company)
    except Exception as e:
        visa_result = {
            "status": "unknown", "source": "none",
            "headline": "⚠️ Visa check could not run",
            "detail": str(e), "color": "warning",
        }
    return {**state, "visa_result": visa_result}


def resume_agent_node(state: JobPrepState) -> JobPrepState:
    retry_count = state.get("retry_count", 0)
    if retry_count > 0:
        missing = (state.get("ats_result") or {}).get("missing_keywords", [])
        current = state.get("resume_output")
        print(f"Regenerating resume (retry {retry_count}) targeting {len(missing)} missing keywords...")
        output = run_resume_agent(
            state["jd_text"], state["parsed_jd"],
            missing_keywords=missing, current_resume=current,
        )
    else:
        print("Tailoring resume...")
        output = run_resume_agent(state["jd_text"], state["parsed_jd"])
    return {**state, "resume_output": output}


def ats_agent_node(state: JobPrepState) -> JobPrepState:
    print("Running ATS keyword gap analysis...")
    ats_result = run_ats_agent(state["resume_output"], state["parsed_jd"])
    return {**state, "ats_result": ats_result}


def evaluator_node(state: JobPrepState) -> JobPrepState:
    print("Running evaluator...")
    eval_result = run_evaluator(
        state["resume_output"], "", state["jd_text"], state["parsed_jd"]
    )
    return {**state, "eval_result": eval_result}


def increment_retry_node(state: JobPrepState) -> JobPrepState:
    """Bumps retry_count before re-entering resume_agent so retries are bounded."""
    return {**state, "retry_count": state.get("retry_count", 0) + 1}


def package_output_node(state: JobPrepState) -> JobPrepState:
    print("Packaging final output...")
    final_output = {
        "role": (state["parsed_jd"] or {}).get("role", ""),
        "company": (state["parsed_jd"] or {}).get("company", ""),
        "resume": state["resume_output"],
        "eval_scores": state["eval_result"],
        "ats_gap": state["ats_result"],
        "visa": state["visa_result"],
    }
    return {**state, "final_output": final_output}


# ---------------------------------------------------------------
# CONDITIONAL EDGE
# ---------------------------------------------------------------

def should_retry(state: JobPrepState) -> str:
    eval_result = state["eval_result"]
    retry_count = state.get("retry_count", 0)
    if eval_result["passes"]:
        print("Quality check passed")
        return "pass"
    elif retry_count < 2:
        print(f"Quality check failed — scheduling retry (current count: {retry_count})")
        return "retry"
    else:
        print("Max retries reached — passing output with warning")
        return "pass"


# ---------------------------------------------------------------
# BUILD THE GRAPH
# ---------------------------------------------------------------

def build_graph():
    graph = StateGraph(JobPrepState)

    graph.add_node("parse_jd", parse_jd_node)
    graph.add_node("visa_check", visa_check_node)
    graph.add_node("resume_agent", resume_agent_node)
    graph.add_node("ats_agent", ats_agent_node)
    graph.add_node("evaluator", evaluator_node)
    graph.add_node("increment_retry", increment_retry_node)
    graph.add_node("package_output", package_output_node)

    graph.set_entry_point("parse_jd")
    graph.add_edge("parse_jd", "visa_check")
    graph.add_edge("visa_check", "resume_agent")
    graph.add_edge("resume_agent", "ats_agent")
    graph.add_edge("ats_agent", "evaluator")

    graph.add_conditional_edges(
        "evaluator",
        should_retry,
        {"pass": "package_output", "retry": "increment_retry"},
    )

    graph.add_edge("increment_retry", "resume_agent")
    graph.add_edge("package_output", END)

    return graph.compile()


# ---------------------------------------------------------------
# TEST ENTRYPOINT
# ---------------------------------------------------------------

if __name__ == "__main__":
    test_jd = """
    Senior AI Product Manager - Google DeepMind

    We are looking for a Senior AI Product Manager to lead our machine learning
    platform products. You will own the roadmap for our ML infrastructure tools,
    work closely with research and engineering teams, and drive adoption across
    the organization.

    Requirements:
    - 5+ years of product management experience
    - Strong understanding of machine learning concepts and MLOps
    - Experience with LLMs, model monitoring, and AI safety
    - Proven ability to work with cross-functional engineering teams
    - Track record of shipping AI products at scale

    Nice to have:
    - Background in data science or ML engineering
    - Experience with agentic AI systems
    - Knowledge of responsible AI practices
    """

    print("Starting agentic job prep system...\n")
    app = build_graph()
    result = app.invoke(make_initial_state(test_jd))

    print("\n--- FINAL OUTPUT ---\n")
    print(f"Role: {result['final_output']['role']}")
    print(f"Company: {result['final_output']['company']}")
    print(f"Visa: {result['visa_result']['headline']}")
    print(f"\nEval Scores: {result['eval_result']}")
    print(f"\nResume Output (first 500 chars):\n{result['resume_output'][:500]}")
