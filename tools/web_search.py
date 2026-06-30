import os
from dotenv import load_dotenv

load_dotenv()


def search_interview_questions(role: str, company: str) -> dict:
    """
    Searches the web for real interview questions reported for this
    specific role and company. Returns a dict with raw results and a
    formatted context string ready to pass to the prep agent.

    Returns:
        {
            "success": bool,
            "context": str,   # formatted for prompt injection
            "message": str    # human-readable status
        }
    """
    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        return {
            "success": False,
            "context": "",
            "message": "TAVILY_API_KEY not set — skipping web search."
        }

    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)
    except Exception as e:
        return {
            "success": False,
            "context": "",
            "message": f"Tavily client error: {e}"
        }

    queries = [
        f"{company} {role} interview questions",
        f"{company} {role} interview process Glassdoor Blind",
        f"how to prepare for {role} interview at {company}",
    ]

    all_results = []
    for query in queries:
        try:
            response = client.search(
                query=query,
                search_depth="basic",
                max_results=3,
                include_answer=False,
            )
            for r in response.get("results", []):
                title = r.get("title", "").strip()
                content = r.get("content", "").strip()
                url = r.get("url", "").strip()
                if content:
                    all_results.append(f"Source: {title} ({url})\n{content}")
        except Exception:
            continue

    if not all_results:
        return {
            "success": False,
            "context": "",
            "message": "Web search returned no usable results — using Claude's training data only."
        }

    context = "\n\n---\n\n".join(all_results)
    return {
        "success": True,
        "context": context,
        "message": f"Found {len(all_results)} search results for '{role} at {company}'."
    }
