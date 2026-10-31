"""Cheap rule-based filters that run before any paid API call."""

import re

OFFICE_5_DAYS = re.compile(
    r"(5|five)\s*days?\s*(a|per|/)?\s*week\s*(from|in|at)?\s*(the\s*)?office"
    r"|work(ing)?\s*from\s*office\s*(all|5|five)"
    r"|fully\s*(in[- ]office|on[- ]?site)"
    r"|100%\s*(in[- ]office|on[- ]?site)",
    re.I,
)
HYBRID = re.compile(r"\bhybrid\b|(2|3|two|three)\s*days?\s*(a|per|/)?\s*week", re.I)
REMOTE = re.compile(r"\b(fully\s*)?remote\b|work\s*from\s*home|\bwfh\b", re.I)


def _any(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text, re.I) for p in patterns)


def title_tier(title: str, prefs: dict) -> str | None:
    """Returns 'primary', 'secondary' or None (drop)."""
    t = prefs["titles"]
    if _any(t["exclude"], title):
        return None
    if _any(t["primary"], title):
        return "primary"
    if _any(t["secondary"], title):
        return "secondary"
    return None


def location_ok(location: str, workplace: str, prefs: dict) -> bool:
    loc = location.lower()
    if any(city in loc for city in prefs["location"]["include"]):
        return True
    remote = "remote" in workplace.lower() or "remote" in loc
    return prefs["location"]["remote_ok"] and remote and "india" in loc


def company_excluded(company: str, prefs: dict) -> bool:
    name = company.lower()
    return any(ex == name or name.startswith(ex + " ") for ex in prefs["exclude_companies"])


def work_mode_hint(text: str, workplace: str = "") -> str:
    """Best guess from keywords: 'office', 'hybrid', 'remote' or 'unknown'."""
    wp = workplace.lower()
    if "remote" in wp:
        return "remote"
    if "hybrid" in wp:
        return "hybrid"
    if OFFICE_5_DAYS.search(text):
        return "office"
    if HYBRID.search(text):
        return "hybrid"
    if REMOTE.search(text):
        return "remote"
    if wp in ("onsite", "on-site", "on_site", "office"):
        return "office"
    return "unknown"
