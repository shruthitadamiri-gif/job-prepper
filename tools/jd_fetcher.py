import ipaddress
import re
import socket
from urllib.parse import urlparse

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


_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


def _validate_url(url: str) -> str | None:
    """
    Returns an error message if the URL is unsafe, else None.
    Rejects non-http(s) schemes, userinfo, and private/reserved IPs.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return "Invalid URL format."

    if parsed.scheme not in ("http", "https"):
        return "Only http and https URLs are allowed."

    if parsed.username or parsed.password:
        return "URLs with credentials (user:pass@host) are not allowed."

    hostname = parsed.hostname
    if not hostname:
        return "URL has no hostname."

    try:
        ip = ipaddress.ip_address(socket.gethostbyname(hostname))
    except Exception:
        return f"Could not resolve hostname: {hostname}"

    for network in _PRIVATE_NETWORKS:
        if ip in network:
            return f"Requests to private/reserved IP ranges are not allowed ({ip})."

    return None


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
    url_error = _validate_url(url)
    if url_error:
        return {"success": False, "jd_text": "", "message": url_error}

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
