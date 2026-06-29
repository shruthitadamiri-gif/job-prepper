import os
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv
from tools.jd_parser import parse_jd
from agents.resume_agent import run_resume_agent
from agents.prep_agent import run_prep_agent
from agents.evaluator import run_evaluator

load_dotenv()

# ---------------------------------------------------------------
# STATE - the shared dictionary every node reads from and writes to
# ---------------------------------------------------------------
class JobPrepState(TypedDict):
    jd_text: str
    parsed_jd: Optional[dict]
    resume_output: Optional[str]
    prep_output: Optional[str]
    eval_result: Optional[dict]
    retry_count: int
    final_output: Optional[dict]

# ---------------------------------------------------------------
# NODES
# ---------------------------------------------------------------

def parse_jd_node(state: JobPrepState) -> JobPrepState:
    print("Parsing job description...")
    parsed = parse_jd(state["jd_text"])
    return {**state, "parsed_jd": parsed}

def resume_agent_node(state: JobPrepState) -> JobPrepState:
    print("Running resume agent...")
    resume_output = run_resume_agent(state["jd_text"], state["parsed_jd"])
    return {**state, "resume_output": resume_output}

def prep_agent_node(state: JobPrepState) -> JobPrepState:
    print("Running interview prep agent...")
    prep_output = run_prep_agent(state["jd_text"], state["parsed_jd"])
    return {**state, "prep_output": prep_output}

def evaluator_node(state: JobPrepState) -> JobPrepState:
    print("Running evaluator...")
    eval_result = run_evaluator(
        state["resume_output"],
        state["prep_output"],
        state["jd_text"],
        state["parsed_jd"]
    )
    return {**state, "eval_result": eval_result}

def package_output_node(state: JobPrepState) -> JobPrepState:
    print("Packaging final output...")
    final_output = {
        "role": state["parsed_jd"].get("role", ""),
        "company": state["parsed_jd"].get("company", ""),
        "resume": state["resume_output"],
        "prep": state["prep_output"],
        "eval_scores": state["eval_result"],
    }
    return {**state, "final_output": final_output}

# ---------------------------------------------------------------
# CONDITIONAL EDGE - the retry logic
# ---------------------------------------------------------------

def should_retry(state: JobPrepState) -> str:
    eval_result = state["eval_result"]
    retry_count = state.get("retry_count", 0)

    if eval_result["passes"]:
        print("Quality check passed - moving to final output")
        return "pass"
    elif retry_count < 2:
        print(f"Quality check failed - retrying (attempt {retry_count + 1})")
        return "retry"
    else:
        print("Max retries reached - passing output with warning")
        return "pass"

# ---------------------------------------------------------------
# BUILD THE GRAPH
# ---------------------------------------------------------------

def build_graph():
    graph = StateGraph(JobPrepState)

    graph.add_node("parse_jd", parse_jd_node)
    graph.add_node("resume_agent", resume_agent_node)
    graph.add_node("prep_agent", prep_agent_node)
    graph.add_node("evaluator", evaluator_node)
    graph.add_node("package_output", package_output_node)

    graph.set_entry_point("parse_jd")
    graph.add_edge("parse_jd", "resume_agent")
    graph.add_edge("resume_agent", "prep_agent")
    graph.add_edge("prep_agent", "evaluator")

    graph.add_conditional_edges(
        "evaluator",
        should_retry,
        {
            "pass": "package_output",
            "retry": "resume_agent"
        }
    )

    graph.add_edge("package_output", END)

    return graph.compile()

# ---------------------------------------------------------------
# RUN
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

    initial_state = {
        "jd_text": test_jd,
        "parsed_jd": None,
        "resume_output": None,
        "prep_output": None,
        "eval_result": None,
        "retry_count": 0,
        "final_output": None
    }

    print("Starting agentic job prep system...\n")
    app = build_graph()
    result = app.invoke(initial_state)

    print("\n--- FINAL OUTPUT ---\n")
    print(f"Role: {result['final_output']['role']}")
    print(f"Company: {result['final_output']['company']}")
    print(f"\nEval Scores: {result['final_output']['eval_scores']}")
    print(f"\nResume Output (first 500 chars):\n{result['final_output']['resume'][:500]}")
