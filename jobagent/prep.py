"""Daily 30-minute interview prep: a different exercise each weekday, getting harder over the months."""

from datetime import date

from . import llm

# Monday = 0
WEEKLY_PLAN = {
    0: ("Product sense case", "Design or improve a product. Clarify, pick users and a problem, prioritise, propose a solution, define success metrics."),
    1: ("Metrics & analytics case", "A metric moved or must be chosen: north-star and guardrail metrics, root-cause analysis, experiment design, trade-offs."),
    2: ("Strategy & business case", "Market entry, build/buy/partner, pricing, platform bets, GCC charter or P&L questions typical of MNC and fintech leadership rounds."),
    3: ("AI product leadership case", "Ship a GenAI or agentic feature: use-case selection, evals, failure modes, cost/latency, rollout, governance, measuring value."),
    4: ("Leadership & behavioural story", "Build one STAR story from the candidate's real experience for a common Director/VP question, then the follow-ups interviewers ask."),
    5: ("Company interview guide", "How one focus company runs its senior product loop: rounds, what each tests, real-style questions, what great looks like, how to prepare."),
    6: ("Rapid-fire Q&A + weekly review", "Ten mixed questions with crisp model answers, then a short self-review checklist for the week."),
}


def phase(today: date, prefs: dict) -> str:
    start = date.fromisoformat(str(prefs["prep"]["search_start"]))
    month = max(0, (today - start).days // 30)
    if month < 2:
        return "Foundation (months 1-2): clear structure, frameworks made explicit, medium difficulty."
    if month < 5:
        return "Company-specific (months 3-5): realistic Director/VP-level cases framed for the focus companies, harder follow-ups."
    return "Interview-ready (months 6-8): full mock-interview intensity, ambiguous prompts, pushback from the interviewer, executive presence."


SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "company_context", "prompt", "how_to_use_30_min", "hints",
                 "model_answer", "what_great_looks_like", "follow_up_questions", "one_thing_to_practise"],
    "properties": {
        "title": {"type": "string"},
        "company_context": {"type": "string", "description": "Which company or kind of company this is modelled on, and why"},
        "prompt": {"type": "string", "description": "The case or question exactly as an interviewer would pose it"},
        "how_to_use_30_min": {"type": "array", "items": {"type": "string"}, "description": "Timed steps adding up to 30 minutes"},
        "hints": {"type": "array", "items": {"type": "string"}},
        "model_answer": {"type": "string", "description": "A strong senior-level answer, in plain paragraphs and short lists"},
        "what_great_looks_like": {"type": "array", "items": {"type": "string"}, "description": "Rubric an interviewer would use"},
        "follow_up_questions": {"type": "array", "items": {"type": "string"}},
        "one_thing_to_practise": {"type": "string"},
    },
}

SYSTEM = """You are a demanding interview coach for a senior product leader targeting
Director / Head of Product / VP Product roles in Bengaluru. You write one daily prep
exercise that takes 30 minutes. Make it specific and realistic - the kind of prompt
actually used in senior product interviews - and tie answers to the candidate's real
experience where it helps. Write in clear, simple English. No filler.

Candidate profile:
{profile}"""


def generate(today: date, profile: str, prefs: dict, recent_titles: list[str]) -> dict:
    topic, brief = WEEKLY_PLAN[today.weekday()]
    focus = ", ".join(prefs["prep"]["focus_companies"])
    avoid = "\n".join(f"- {t}" for t in recent_titles[:40]) or "- (none yet)"
    user = (
        f"Today's exercise type: {topic}\n{brief}\n\n"
        f"Stage of preparation: {phase(today, prefs)}\n"
        f"Focus companies: {focus}\n\n"
        f"Do not repeat these recent exercises:\n{avoid}"
    )
    result = llm.ask_json(SYSTEM.format(profile=profile), user, SCHEMA, effort="high", max_tokens=32000)
    result["topic"] = topic
    return result
