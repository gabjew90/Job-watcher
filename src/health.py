"""Per-run source health log, committed to state/source_health.json.

Every fetcher records each attempt here. Two failure modes matter for
maintenance: loud (exception → status ✗) and silent (fetch "succeeds" with
zero results, e.g. a WAF serving an empty page → status ⚠). The summary
tracks the last date each source actually produced results, so a fetcher
that quietly died weeks ago is visible on the dashboard and in the digest.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

FILE = Path("state/source_health.json")
MAX_RUNS = 120  # ~4 months of daily history

_current: dict[str, dict] = {}


def record(source: str, ok: bool, count: int = 0, error: str | None = None) -> None:
    entry = _current.setdefault(source, {"ok": False, "count": 0, "error": None})
    entry["ok"] = entry["ok"] or ok  # healthy if any attempt for it succeeded
    entry["count"] += count
    if error and entry["error"] is None:
        entry["error"] = str(error)[:200]


def _load_runs() -> list[dict]:
    if FILE.exists():
        return json.loads(FILE.read_text()).get("runs", [])
    return []


def save_run() -> None:
    runs = _load_runs()
    runs.append({
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "sources": _current,
    })
    FILE.parent.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps({"runs": runs[-MAX_RUNS:]}, indent=1) + "\n")


def summary() -> list[dict]:
    """Latest status per source, plus the last date it produced results."""
    runs = _load_runs()
    if not runs:
        return []
    latest = runs[-1]
    out = []
    for source, entry in sorted(latest["sources"].items()):
        last_results = next(
            (r["date"][:10] for r in reversed(runs)
             if r["sources"].get(source, {}).get("count", 0) > 0),
            None,
        )
        status = "ok" if entry["ok"] and entry["count"] > 0 else (
            "empty" if entry["ok"] else "failed")
        out.append({
            "source": source,
            "status": status,
            "count": entry["count"],
            "error": entry.get("error"),
            "last_results": last_results,
        })
    return out
