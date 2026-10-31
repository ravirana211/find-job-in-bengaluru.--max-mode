"""Claude reads each shortlisted job description and judges fit, work mode and pay."""

from . import llm

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "level", "fit_score", "work_mode", "office_days_per_week", "office_location",
        "stated_ctc_lpa", "estimated_ctc_lpa_low", "estimated_ctc_lpa_high", "salary_confidence",
        "company_reputation", "why_fit", "gaps", "pitch", "summary",
    ],
    "properties": {
        "level": {"type": "string", "description": "Role level, e.g. Senior PM, Principal PM, Director, VP"},
        "fit_score": {"type": "integer", "description": "0-100 fit for this candidate"},
        "work_mode": {"type": "string", "enum": ["remote", "hybrid", "office", "unknown"]},
        "office_days_per_week": {"type": ["integer", "null"]},
        "office_location": {"type": "string", "description": "Office area in Bengaluru named in the post, or empty"},
        "stated_ctc_lpa": {"type": ["number", "null"], "description": "Max CTC stated in the post, in INR lakhs per annum"},
        "estimated_ctc_lpa_low": {"type": "number"},
        "estimated_ctc_lpa_high": {"type": "number"},
        "salary_confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "company_reputation": {"type": "integer", "description": "1-5: brand, stability, employee ratings as a place to work"},
        "why_fit": {"type": "array", "items": {"type": "string"}, "description": "2-4 specific reasons"},
        "gaps": {"type": "array", "items": {"type": "string"}, "description": "0-3 honest gaps or risks"},
        "pitch": {"type": "string", "description": "One-line angle the candidate should lead with"},
        "summary": {"type": "string", "description": "One-line summary of the role"},
    },
}

SYSTEM = """You screen job openings for one candidate: a senior product leader in Bengaluru.
Judge each posting honestly. Do not inflate fit scores.

Salary: estimate total CTC excluding ESOPs, in INR lakhs per annum (LPA), for this role
level at this company in Bengaluru, using what you know about the company's pay bands,
funding stage and market rates. Use salary_confidence "low" when you are guessing.
If the post states pay in another currency or per month, convert to LPA.

Work mode: read the post for office expectations. "hybrid" with no day count means
office_days_per_week = null.

Company reputation (1-5): 5 = top global brand or top-tier Indian product company known
as a great place to work; 3 = decent but mixed; 1 = poor reviews or unstable.

Candidate profile:
{profile}"""


def analyse(job: dict, profile: str) -> dict:
    user = (
        f"Company: {job['company']}\n"
        f"Title: {job['title']}\n"
        f"Location: {job['location']}\n"
        f"Board work-mode field: {job.get('workplace') or 'n/a'}\n\n"
        f"Job description:\n{job['description'] or '(not available)'}"
    )
    return llm.ask_json(SYSTEM.format(profile=profile), user, SCHEMA, effort="low")


def pay_verdict(analysis: dict, prefs: dict) -> str:
    """'ok', 'too_low' or 'unknown_ok' (pay unknown but company is strong)."""
    floor = prefs["salary"]["min_ctc_lpa"]
    stated = analysis.get("stated_ctc_lpa")
    if stated:
        return "ok" if stated >= floor else "too_low"
    if analysis["estimated_ctc_lpa_high"] < floor and analysis["salary_confidence"] != "low":
        return "too_low"
    if analysis["estimated_ctc_lpa_high"] >= floor:
        return "ok"
    if analysis["company_reputation"] >= prefs["salary"]["min_reputation_if_unknown"]:
        return "unknown_ok"
    return "too_low"
