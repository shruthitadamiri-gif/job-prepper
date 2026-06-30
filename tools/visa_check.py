import os
import re
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------
# Keyword patterns
# ---------------------------------------------------------------

_WILL_NOT_SPONSOR = [
    r"will not sponsor",
    r"unable to (provide|offer) (visa |work )?sponsorship",
    r"cannot (provide|offer|support) (visa |work )?sponsorship",
    r"no (visa )?sponsorship",
    r"sponsorship (is )?not available",
    r"not able to sponsor",
    r"does not sponsor",
    r"must (be|have) (legally )?authorized to work",
    r"must be (eligible|authorized) to work (in|for) (the )?u\.?s\.?",
    r"(citizen|permanent resident|green card|ead).*only",
    r"without (the need for|requiring|requiring current or future).*sponsorship",
    r"not (provide|consider|offer).*work authorization",
    r"unrestricted.*work authorization",
]

_WILL_SPONSOR = [
    r"will (provide|offer|support|consider) (visa |work )?sponsorship",
    r"(visa |work )?sponsorship (is )?available",
    r"sponsorship (will be |is )?provided",
    r"h[\-]?1b",
    r"we sponsor",
    r"open to sponsoring",
    r"eligible for sponsorship",
    r"can (provide|offer) sponsorship",
]


def _scan_jd(jd_text: str) -> dict | None:
    """
    Scan the JD for explicit sponsorship language.
    Returns a result dict if found, None if the JD is silent.
    """
    text = jd_text.lower()

    for pattern in _WILL_NOT_SPONSOR:
        if re.search(pattern, text):
            snippet = _extract_snippet(jd_text, pattern)
            return {
                "status": "not_sponsored",
                "source": "jd",
                "headline": "❌ This role does NOT offer visa sponsorship",
                "detail": f'The JD explicitly states: "{snippet}"',
                "color": "error",
            }

    for pattern in _WILL_SPONSOR:
        if re.search(pattern, text):
            snippet = _extract_snippet(jd_text, pattern)
            return {
                "status": "sponsored",
                "source": "jd",
                "headline": "✅ This role offers visa sponsorship",
                "detail": f'The JD mentions: "{snippet}"',
                "color": "success",
            }

    return None


def _extract_snippet(text: str, pattern: str, context: int = 120) -> str:
    """Return a short snippet of text around the matched pattern."""
    m = re.search(pattern, text, re.IGNORECASE)
    if not m:
        return ""
    start = max(0, m.start() - 30)
    end = min(len(text), m.end() + context)
    snippet = text[start:end].strip()
    # Capitalize first char and add ellipsis if truncated
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
    return snippet


def _search_h1b_history(company: str) -> dict:
    """
    Use Tavily to search public H1B sponsorship history for the company.
    Looks at myvisajobs.com, h1bdata.info, and USCIS disclosure data.
    """
    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        return {
            "status": "unknown",
            "source": "none",
            "headline": "⚠️ Sponsorship not mentioned in JD — could not search (no Tavily key)",
            "detail": "Add TAVILY_API_KEY to .env to enable H1B history lookup.",
            "color": "warning",
        }

    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)
    except Exception as e:
        return {
            "status": "unknown",
            "source": "none",
            "headline": "⚠️ Sponsorship not mentioned in JD — search failed",
            "detail": str(e),
            "color": "warning",
        }

    queries = [
        f"{company} H1B visa sponsorship site:myvisajobs.com OR site:h1bdata.info",
        f"{company} H1B sponsorship history USCIS LCA",
        f"does {company} sponsor H1B visas",
    ]

    combined = ""
    for query in queries:
        try:
            resp = client.search(query=query, search_depth="basic", max_results=4)
            for r in resp.get("results", []):
                combined += f"\n{r.get('title','')} — {r.get('content','')[:300]}"
        except Exception:
            continue

    if not combined:
        return {
            "status": "unknown",
            "source": "web",
            "headline": "⚠️ Sponsorship not mentioned in JD — no web data found",
            "detail": f"Could not find H1B history for {company} in public data sources. Verify directly on myvisajobs.com.",
            "color": "warning",
        }

    # Interpret results
    lower = combined.lower()
    strong_yes = sum(1 for p in [
        r"\bsponsors?\b", r"h[\-]?1b petition", r"lca filing", r"certified lca",
        r"\d+\s*(h[\-]?1b|visa)", r"approved petition"
    ] if re.search(p, lower))

    strong_no = sum(1 for p in [
        r"does not sponsor", r"no h[\-]?1b", r"not sponsor", r"no sponsorship record"
    ] if re.search(p, lower))

    # Try to extract a petitions count
    count_match = re.search(r"(\d[\d,]+)\s*(h[\-]?1b|lca|petition|visa)", lower)
    count_str = f" (~{count_match.group(1)} H1B petitions on record)" if count_match else ""

    if strong_no > strong_yes:
        return {
            "status": "likely_no",
            "source": "web",
            "headline": f"🔶 Sponsorship not in JD — public data suggests {company} rarely sponsors",
            "detail": f"Web search of H1B/LCA public records found limited or no sponsorship history for {company}. Confirm directly with the recruiter.",
            "color": "warning",
        }
    elif strong_yes >= 2:
        return {
            "status": "likely_yes",
            "source": "web",
            "headline": f"🟡 Sponsorship not in JD — {company} has H1B history{count_str}",
            "detail": f"Public H1B/LCA data shows {company} has sponsored work visas in the past. This doesn't guarantee sponsorship for this role — confirm with the recruiter.",
            "color": "info",
        }
    else:
        return {
            "status": "unknown",
            "source": "web",
            "headline": f"⚠️ Sponsorship not mentioned in JD — {company}'s history is unclear",
            "detail": f"Public H1B data for {company} is inconclusive. Check myvisajobs.com directly or ask the recruiter.",
            "color": "warning",
        }


# ---------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------

def check_visa_sponsorship(jd_text: str, company: str) -> dict:
    """
    Two-phase check:
    1. Scan the JD text for explicit sponsorship language.
    2. If the JD is silent, search public H1B records for the company.

    Returns a dict:
      {
        "status":   "sponsored" | "not_sponsored" | "likely_yes" | "likely_no" | "unknown",
        "source":   "jd" | "web" | "none",
        "headline": str,   # short summary for the banner
        "detail":   str,   # one-sentence explanation with source
        "color":    "success" | "error" | "warning" | "info"
      }
    """
    jd_result = _scan_jd(jd_text)
    if jd_result:
        return jd_result

    return _search_h1b_history(company)


if __name__ == "__main__":
    # Quick tests
    jd_no = "We are unable to provide visa sponsorship for this role. Candidates must be authorized to work in the US."
    jd_yes = "We will provide H1B sponsorship for the right candidate."
    jd_silent = "Senior AI Product Manager at Google. Requirements: 5+ years PM experience, MLOps knowledge."

    for label, jd in [("NO", jd_no), ("YES", jd_yes), ("SILENT", jd_silent)]:
        result = check_visa_sponsorship(jd, "Google")
        print(f"\n[{label}]")
        print(" status:", result["status"])
        print(" source:", result["source"])
        print(" headline:", result["headline"])
        print(" detail:", result["detail"])
