import re
import requests
from bs4 import BeautifulSoup

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}
REQUEST_TIMEOUT_SECONDS = 10
MIN_VALID_TEXT_LENGTH = 200


def _looks_garbled(text: str) -> bool:
    """
    Heuristic check for pages that loaded but didn't yield readable
    job-description text — e.g. a JS-rendered shell with almost no
    visible text, or a bot-block/CAPTCHA page.
    """
    if len(text) < MIN_VALID_TEXT_LENGTH:
        return True

    letters = re.findall(r"[A-Za-z]", text)
    if len(letters) < 100:
        return True

    block_phrases = [
        "enable javascript",
        "are you a robot",
        "captcha",
        "access denied",
        "verify you are human",
        "just a moment",
    ]
    lowered = text.lower()
    if any(phrase in lowered for phrase in block_phrases):
        return True

    return False


def fetch_jd_from_url(url: str) -> dict:
    """
    Fetches a job posting URL and extracts visible text as the job
    description. Never raises — always returns a dict describing what
    happened so the caller can show the user a clear message.

    Returns:
        {
            "success": bool,
            "jd_text": str,      # extracted text, "" on failure
            "message": str       # human-readable explanation
        }
    """
    try:
        response = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.exceptions.Timeout:
        return {
            "success": False,
            "jd_text": "",
            "message": f"The request to {url} timed out after {REQUEST_TIMEOUT_SECONDS}s. "
                       "Please paste the job description text instead."
        }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "jd_text": "",
            "message": f"Couldn't reach that URL ({e}). Please paste the job description text instead."
        }

    if response.status_code != 200:
        return {
            "success": False,
            "jd_text": "",
            "message": f"The page returned HTTP {response.status_code}, so it couldn't be fetched. "
                       "Please paste the job description text instead."
        }

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()

    if _looks_garbled(text):
        return {
            "success": False,
            "jd_text": "",
            "message": "That page didn't return readable job description text — it may load "
                       "content via JavaScript or block automated requests. Please paste the "
                       "job description text instead."
        }

    return {
        "success": True,
        "jd_text": text,
        "message": f"Fetched {len(text)} characters of job description text from the URL."
    }


if __name__ == "__main__":
    result = fetch_jd_from_url("https://example.com")
    print(result["success"], "-", result["message"])
    print(result["jd_text"][:300])
