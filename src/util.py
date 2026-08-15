import html
import re

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": BROWSER_UA, "Accept-Language": "en-US,en;q=0.9"}


def strip_html(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_pay(text: str) -> str:
    """Pull a salary range out of free text (US pay-transparency style)."""
    if not text:
        return ""
    m = re.search(
        r"(?:USD\s?)?\$\s?\d[\d,.]*\s?[kK]?\s?(?:[-–—]|to)\s?"
        r"(?:USD\s?)?\$?\s?\d[\d,.]*\s?[kK]?(?:\s?(?:per|/)\s?\w+)?",
        text)
    if not m:  # single figure, only if clearly a salary-sized amount
        m = re.search(r"\$\s?\d{2,3},\d{3}(?:\.\d+)?", text)
    return re.sub(r"\s+", " ", m.group(0)).strip() if m else ""


def infer_work_mode(title: str, location: str, description: str) -> str:
    """Best-effort onsite/hybrid/remote from text; structured fields win
    over this in the fetchers that have them."""
    strong = f"{title} {location}".lower()
    desc = (description or "").lower()
    if "hybrid" in strong or "hybrid" in desc:
        return "hybrid"
    if "remote" in strong:
        return "remote"
    if re.search(r"\b(?:fully|100%)?\s?remote\b", desc) and "not remote" not in desc:
        return "remote"
    if re.search(r"\bon-?\s?site\b", desc):
        return "onsite"
    return ""
