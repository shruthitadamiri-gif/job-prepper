import re
import json


def parse_llm_json(raw: str) -> dict:
    """
    Parse JSON from an LLM response that may be wrapped in markdown fences.

    Strategy:
    1. Strip ```json ... ``` or ``` ... ``` fences with a proper regex (not str.strip)
    2. Try json.loads on the cleaned text
    3. On failure, extract the first {...} block and retry
    4. On second failure, raise a clear ValueError including the first 200 chars
    """
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", raw.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\n?```\s*$", "", cleaned.strip()).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Fall back: extract the outermost {...} block
    m = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(
        f"Could not parse JSON from LLM response. "
        f"First 200 chars: {raw[:200]!r}"
    )
