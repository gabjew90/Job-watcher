import html
import re
from urllib.parse import urlparse

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": BROWSER_UA, "Accept-Language": "en-US,en;q=0.9"}


# Employers whose sources disagree on their own name. Without these, an
# acronym and a spelled-out name key differently and the same posting shows
# up twice (Indeed "Pacific Gas and Electric" vs careers site "PG&E").
# Extend as new variants appear; only ever merge names of the SAME company.
COMPANY_ALIASES = {
    "pge": ("pacific gas", "pg&e", "pge corporation"),
    "sce": ("southern california edison", "edison international"),
    "sdge": ("san diego gas", "sdg&e"),
    "sempra": ("sempra",),
    "google": ("alphabet", "google"),
    "meta": ("meta platforms", "facebook"),
    "amazon": ("amazon", "amazon web services", "aws"),
    "nextera": ("nextera", "florida power & light"),
    "gevernova": ("ge vernova", "general electric vernova"),
    "lges": ("lg energy solution", "lg chem"),
    "servicetitan": ("servicetitan", "service titan"),
    "corescientific": ("core scientific",),
    "appliednova": ("applied digital",),
    # "amd" alone would also match Amdocs; only the spelled-out form maps.
    "amd": ("advanced micro devices",),
    "flex": ("flextronics", "flex ltd"),
}


def company_key(company: str) -> str:
    """Normalize company for cross-source twin matching (Amazon.com Services
    LLC == Amazon Web Services == Amazon; PG&E == Pacific Gas and Electric)."""
    raw = (company or "").lower()
    for canonical, variants in COMPANY_ALIASES.items():
        if any(v in raw for v in variants):
            return canonical
    c = re.sub(r"[^a-z0-9 ]", "", raw.replace(".com", ""))
    c = re.sub(r"\b(inc|llc|corp|corporation|company|services|ltd|co)\b", "", c).strip()
    return c.split()[0] if c.split() else ""


def title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (title or "").lower())[:40]


def city_key(location: str) -> str:
    """First locality token: 'Herndon, Virginia, USA' == 'Herndon, VA'."""
    return re.sub(r"[^a-z]", "", (location or "").split(",")[0].lower())


def twin_key(company: str, title: str, location: str) -> tuple:
    return (company_key(company), title_key(title), city_key(location))


def source_id(url: str) -> str:
    """The ATS's own id for a posting, from its URL.

    Titles change — an employer renamed a role and it looked like the old
    posting closed and a brand new one appeared. The ATS id is stable
    across renames, so it is the strongest identity we have.
    """
    if not url:
        return ""
    m = re.search(r"[?&](?:gh_jid|jk|jobId|id)=([A-Za-z0-9-]+)", url)
    if m:
        return m.group(1)
    # Radancy-style paths put the id BEFORE the slug: /job/<id>/<title-slug>/
    m = re.search(r"/job/(\d{4,})/", url)
    if m:
        return m.group(1)
    tail = url.rstrip("/").split("/")[-1].split("?")[0]
    # numeric id, uuid, or a requisition code like R24478-1
    if re.fullmatch(r"\d{4,}|[0-9a-f]{8}-[0-9a-f-]{20,}|[A-Z]{1,3}\d{3,}[-\w]*", tail):
        return tail
    m = re.search(r"_([A-Z]{1,3}\d{3,}[-\w]*)$", tail)
    return m.group(1) if m else ""


def group_key(company: str, title: str) -> tuple:
    """Same company + title = ONE opening, however many metros it is posted
    to. Employers and aggregators syndicate a single req city-by-city (a
    remote role appeared in 19 cities), which is the main source of visible
    duplicates. Extra locations are kept on the surviving record."""
    return (company_key(company), title_key(title))


def strip_html(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_pay(text: str) -> str:
    """Pull a salary range out of free text (US pay-transparency style)."""
    if not text:
        return ""
    # "Minimum: $126,000 ... Maximum: $200,000" (PG&E and other utilities):
    # the first pair is the posting's headline locality.
    # Also "Minimum Base Salary (Bay Area) $140,000.00 ... Maximum ..." and
    # "CA Minimum, $161,520 CA Maximum, $207,504".
    # Only in a pay context, so a "Minimum $5,000 relocation" line is not
    # read as salary; an hourly unit after the maximum is kept.
    text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)  # zero-width spaces ("$\u200b122,000")
    for m in re.finditer(r"\bMin(?:imum)?\b[^$]{0,40}\$\s?(\d[\d,]*(?:\.\d+)?)"
                         r"(?:(?!\bMin(?:imum)?\b).){0,160}?"  # a pair never spans another minimum
                         r"\bMax(?:imum)?\b[^$]{0,40}\$\s?(\d[\d,]*(?:\.\d+)?)", text, re.S | re.I):
        if re.search(r"bonus|relocation|signing|stipend", m.group(0), re.I):
            continue
        label = m.group(0)[:m.group(0).find("$")]  # "Minimum Base Salary (Bay Area)"
        if not re.search(r"\b(?:salary|pay|compensation|wages?)\b",
                         text[max(0, m.start() - 600):m.start()] + label, re.I):
            continue
        lo, hi = (re.sub(r"\.00$", "", g) for g in m.groups())
        hourly = re.match(r"\s*(?:per hour|/\s?h(?:ou)?r|hourly)", text[m.end():m.end() + 20], re.I)
        return f"${lo}–${hi}" + ("/hr" if hourly else "")
    m = re.search(
        r"(?:USD\s?)?\$\s?\d[\d,.]*\s?[kK]?\s?(?:[-–—]|to)\s?"
        r"(?:USD\s?)?\$?\s?\d[\d,.]*\s?[kK]?(?:\s?(?:per|/)\s?\w+)?",
        text)
    if not m:  # single figure, only if clearly a salary-sized amount
        m = re.search(r"\$\s?\d{2,3},\d{3}(?:\.\d+)?", text)
    return re.sub(r"\s+", " ", m.group(0)).strip() if m else ""


# Work-arrangement phrasing only. A bare word misfires in this field:
# "remote diagnostics", "remote monitoring", "hybrid inverter", "hybrid
# solar + storage", "on-site generation" describe products and plants, not
# where the job is done (Tesla Staff PM, 2026-10-23: "remote diagnostics"
# made a Palo Alto role read remote; 449 of 624 remote labels had no remote
# location).
_REMOTE = re.compile(
    r"\b(?:fully|100%|completely|entirely)\s+remote\b"
    r"|\bremote[- ](?:first|eligible|friendly|based|position|role|job|work(?:er|ing|force)?"
    r"|opportunit\w*|option|employee|candidates?|from)\b"
    r"|\bwork(?:ing)?\s+(?:fully\s+|100%\s+)?remote(?:ly)?\b"
    r"|\b(?:can|may|will)\s+be\s+(?:performed\s+|done\s+|based\s+)?remote(?:ly)?\b"
    r"|\b(?:is|as)\s+an?\s+(?:fully\s+)?remote\s+(?:role|position|job|opportunity)\b"
    r"|\bthis\s+(?:role|position|job)\s+is\s+(?:fully\s+)?remote\b"
    r"|\bwork\s+from\s+(?:home|anywhere)\b|\bwfh\b"
    r"|\bremote\s*(?:\(|-|,|/)\s*(?:us|usa|u\.s\.|united states|north america)\b"
    r"|\bopen\s+to\s+remote\b", re.I)
_NOT_REMOTE = re.compile(
    r"\b(?:not|non)[- ](?:a\s+)?remote\b|\bremote\s+work\s+is\s+not\b"
    r"|\bno\s+remote\b|\bnot\s+eligible\s+for\s+remote\b", re.I)
_HYBRID = re.compile(
    r"\bhybrid\s+(?:work(?:ing|place)?|schedule|role|position|model|arrangement|environment"
    r"|opportunity|setting|policy|basis|in-office)\b"
    r"|\b(?:is|as)\s+an?\s+hybrid\s+(?:role|position|job)\b"
    r"|\b(?:\d|one|two|three|four)\s*(?:\+\s*)?days?\s+(?:per|a|each)\s+week\s+(?:in|on)[- ]"
    r"(?:the\s+)?(?:office|site)\b"
    r"|\b(?:\d|one|two|three|four)\s*(?:\+\s*)?days?\s+(?:in|on)[- ](?:the\s+)?(?:office|site)\b"
    r"|\b(?:role|position|job|schedule)\s+is\s+(?:a\s+)?hybrid\b|\bhybrid\s+mobility\b"
    r"|\bwork\s+(?:location|arrangement|type)\s*:\s*hybrid\b"
    r"|\bhybrid\s*\(|\(\s*hybrid\s*\)", re.I)
_ONSITE = re.compile(
    r"\b(?:fully|100%|5\s+days)\s+(?:on-?\s?site|in[- ](?:the[- ])?office|in[- ]person)\b"
    r"|\b(?:on-?\s?site|in[- ]office|in[- ]person)\s+(?:role|position|job|work(?:er)?|requirement"
    r"|presence|attendance|schedule|basis|5\s+days)\b"
    r"|\b(?:work(?:ing)?|report(?:ing)?|be\s+based|located)\s+(?:on-?\s?site|in[- ](?:the[- ])?office)\b"
    r"|\bthis\s+(?:role|position|job)\s+is\s+(?:fully\s+)?(?:on-?\s?site|in[- ]office|in[- ]person)\b"
    r"|\bon-?\s?site\s*(?:\(|-|,)\s*(?:no remote|not remote)", re.I)


def infer_work_mode(title: str, location: str, description: str) -> str:
    """Best-effort onsite/hybrid/remote from text; structured fields win
    over this in the fetchers that have them. Title and location are short
    and literal ("Remote - Texas", "(Hybrid)"), so a bare word counts there;
    the description must use work-arrangement phrasing (see _REMOTE)."""
    strong = f"{title} {location}".lower()
    desc = description or ""
    if "hybrid" in strong or _HYBRID.search(desc):
        return "hybrid"
    if "remote" in strong:
        return "remote"
    if _REMOTE.search(desc) and not _NOT_REMOTE.search(desc):
        return "remote"
    if _ONSITE.search(desc):
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


# Sources whose links die on their own schedule, independent of the
# employer's posting.
AGGREGATOR_SOURCES = {"indeed", "glassdoor", "zip_recruiter", "google"}
AGGREGATOR_HOSTS = ("indeed.com", "glassdoor.com", "ziprecruiter.com", "linkedin.com")


def best_link(rec: dict) -> str:
    """The link a person should click. An aggregator copy dies on its own
    schedule, so when an aggregator record carries the employer's own apply
    link, that is the one shown. rec["url"] stays the aggregator's: expiry
    checks the listing through it."""
    apply = rec.get("apply_url") or ""
    if rec.get("source") in AGGREGATOR_SOURCES and apply.startswith("http"):
        host = (urlparse(apply).hostname or "").lower()
        if not any(host == h or host.endswith("." + h) for h in AGGREGATOR_HOSTS):
            return apply
    return rec.get("url", "")
