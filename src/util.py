import html
import re

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": BROWSER_UA, "Accept-Language": "en-US,en;q=0.9"}


def company_key(company: str) -> str:
    """Normalize company for cross-source twin matching (Amazon.com Services
    LLC == Amazon Web Services == Amazon)."""
    c = re.sub(r"[^a-z0-9 ]", "", (company or "").lower().replace(".com", ""))
    c = re.sub(r"\b(inc|llc|corp|corporation|company|services|ltd|co)\b", "", c).strip()
    return c.split()[0] if c.split() else ""


def title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (title or "").lower())[:40]


def city_key(location: str) -> str:
    """First locality token: 'Herndon, Virginia, USA' == 'Herndon, VA'."""
    return re.sub(r"[^a-z]", "", (location or "").split(",")[0].lower())


def twin_key(company: str, title: str, location: str) -> tuple:
    return (company_key(company), title_key(title), city_key(location))


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


ROLE_MARKERS = (
    "what you'll do", "what you will do", "responsibilities", "the role",
    "in this role", "about the role", "about this role", "your impact",
    "position summary", "job summary", "key duties", "what you'll bring",
    "qualifications", "requirements", "you will",
)


def role_excerpt(description: str, limit: int) -> str:
    """Excerpt the part of a posting that describes the ROLE.

    Many postings open with company boilerplate ("About X…") long enough to
    consume the whole prompt budget, starving the scorer of actual scope —
    which then reads as "scope unclear" and depresses the band. When a
    role-content marker appears after leading boilerplate, start there.
    """
    if not description or len(description) <= limit:
        return description or ""
    low = description.lower()
    starts = [low.find(m) for m in ROLE_MARKERS]
    hits = [i for i in starts if i > 150]
    if hits:
        start = max(0, min(hits) - 100)
        return description[start:start + limit]
    return description[:limit]
