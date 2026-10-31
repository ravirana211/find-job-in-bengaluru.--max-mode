"""Builds the daily job digest and prep emails (HTML + plain text)."""

from html import escape

STYLE = "font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1f2328;line-height:1.5;max-width:720px"
MUTED = "color:#57606a;font-size:13px"


def _pay(a: dict, verdict: str) -> str:
    if a.get("stated_ctc_lpa"):
        return f"₹{a['stated_ctc_lpa']:.0f} LPA (stated)"
    band = f"₹{a['estimated_ctc_lpa_low']:.0f}–{a['estimated_ctc_lpa_high']:.0f} LPA est. ({a['salary_confidence']} confidence)"
    return band + (" · pay unknown, strong company" if verdict == "unknown_ok" else "")


def _mode(a: dict) -> str:
    mode = a["work_mode"]
    if mode == "hybrid" and a.get("office_days_per_week"):
        return f"Hybrid, {a['office_days_per_week']} office days/week"
    if mode == "unknown":
        return "Work mode not stated ⚠ verify"
    if mode == "hybrid":
        return "Hybrid (days not stated ⚠ verify)"
    return mode.capitalize()


def _commute(c: dict | None, mode: str) -> str:
    if mode == "remote":
        return "Remote"
    if not c or c.get("verdict") == "unknown":
        return "Office location unclear ⚠ verify"
    parts = [f"{label} {c[key]} min" for key, label in (("car", "🚗"), ("bike", "🏍"), ("metro", "🚇")) if c.get(key) is not None]
    return f"{' · '.join(parts)} to {c['destination']}"


def job_card(job: dict) -> str:
    a, c = job["analysis"], job["commute"]
    why = "".join(f"<li>{escape(x)}</li>" for x in a["why_fit"])
    gaps = "".join(f"<li>{escape(x)}</li>" for x in a["gaps"])
    return f"""
<div style="border:1px solid #d0d7de;border-radius:8px;padding:14px 16px;margin:14px 0">
  <div style="font-size:17px;font-weight:600">
    <a href="{escape(job['url'])}" style="color:#0969da;text-decoration:none">{escape(job['title'])}</a>
    <span style="font-weight:400"> · {escape(job['company'])}</span>
  </div>
  <div style="{MUTED}">{escape(a['level'])} · Fit {a['fit_score']}/100 · Company rating {a['company_reputation']}/5</div>
  <div style="margin-top:6px">{escape(a['summary'])}</div>
  <table style="margin-top:8px;font-size:14px;border-collapse:collapse">
    <tr><td style="padding:2px 10px 2px 0">💰</td><td>{escape(_pay(a, job.get('pay_verdict', '')))}</td></tr>
    <tr><td style="padding:2px 10px 2px 0">🏢</td><td>{escape(_mode(a))}</td></tr>
    <tr><td style="padding:2px 10px 2px 0">📍</td><td>{escape(_commute(c, a['work_mode']))}</td></tr>
  </table>
  <div style="margin-top:8px;font-size:14px"><b>Why it fits</b><ul style="margin:4px 0">{why}</ul></div>
  {f'<div style="font-size:14px"><b>Gaps / risks</b><ul style="margin:4px 0">{gaps}</ul></div>' if gaps else ''}
  <div style="font-size:14px"><b>Lead with:</b> {escape(a['pitch'])}</div>
  <div style="margin-top:10px"><a href="{escape(job['url'])}" style="background:#1f883d;color:#fff;padding:6px 14px;border-radius:6px;text-decoration:none;font-size:14px">View &amp; apply</a></div>
</div>"""


def digest(jobs: list[dict], stats: dict, today: str) -> tuple[str, str, str]:
    jobs = sorted(jobs, key=lambda j: j["analysis"]["fit_score"], reverse=True)
    subject = f"{len(jobs)} new Product role{'s' if len(jobs) != 1 else ''} near you · {today}" if jobs \
        else f"No new matching roles today · {today}"
    cards = "".join(job_card(j) for j in jobs) or "<p>No new roles passed all your filters today. The agent will check again tomorrow.</p>"
    rejected = ", ".join(f"{k}: {v}" for k, v in sorted(stats.get("rejected", {}).items())) or "none"
    broken = stats.get("broken_feeds", [])
    html = f"""<div style="{STYLE}">
<h2 style="margin-bottom:4px">Your Product role digest</h2>
<div style="{MUTED}">{today} · Hybrid/remote · ≥ ₹60 LPA · ≤ 40 min by road or ≤ 60 min by metro</div>
{cards}
<hr style="border:none;border-top:1px solid #d0d7de;margin:24px 0 8px">
<div style="{MUTED}">
Scanned {stats.get('companies_scanned', 0)} company boards, {stats.get('postings_seen', 0)} postings;
{stats.get('new_candidates', 0)} new title matches; filtered out — {escape(rejected)}.<br>
{('Boards not reachable: ' + escape(', '.join(broken))) if broken else 'All company boards reachable.'}
</div></div>"""
    text = "\n\n".join(
        f"{j['title']} — {j['company']} (fit {j['analysis']['fit_score']})\n{j['url']}" for j in jobs
    ) or "No new matching roles today."
    return subject, html, text


def prep_email(p: dict, today: str) -> tuple[str, str, str]:
    def ul(items):
        return "<ul>" + "".join(f"<li>{escape(i)}</li>" for i in items) + "</ul>"

    def paras(text):
        return "".join(f"<p>{escape(par).replace(chr(10), '<br>')}</p>" for par in text.split("\n\n"))

    subject = f"Prep · {p['topic']}: {p['title']} · {today}"
    html = f"""<div style="{STYLE}">
<div style="{MUTED}">Daily prep · {escape(p['topic'])} · 30 minutes</div>
<h2 style="margin-top:4px">{escape(p['title'])}</h2>
<div style="{MUTED}">{escape(p['company_context'])}</div>
<h3>The question</h3>
<div style="background:#f6f8fa;border-left:4px solid #0969da;padding:10px 14px">{paras(p['prompt'])}</div>
<h3>Your 30 minutes</h3>{ul(p['how_to_use_30_min'])}
<h3>Hints</h3>{ul(p['hints'])}
<p style="{MUTED};margin-top:28px">↓ Try it yourself first. Model answer below. ↓</p>
<div style="height:220px"></div>
<h3>Model answer</h3>{paras(p['model_answer'])}
<h3>What great looks like</h3>{ul(p['what_great_looks_like'])}
<h3>Follow-up questions to expect</h3>{ul(p['follow_up_questions'])}
<h3>Practise today</h3><p>{escape(p['one_thing_to_practise'])}</p>
</div>"""
    text = f"{p['title']}\n\n{p['prompt']}\n\nModel answer:\n{p['model_answer']}"
    return subject, html, text
