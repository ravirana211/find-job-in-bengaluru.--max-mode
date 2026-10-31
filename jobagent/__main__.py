"""Daily pipeline.

    python -m jobagent run        # collect jobs, score, email digest + prep
    python -m jobagent jobs       # job digest only
    python -m jobagent prep       # prep email only
    python -m jobagent check      # show missing settings and company-board health
Add --dry-run to write the emails to out/ instead of sending them.
"""

import argparse
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from . import commute, emails, filters, llm, mailer, prep, scorer
from .config import ROOT, load_settings
from .db import DB
from .sources import ats

IST = ZoneInfo("Asia/Kolkata")
MAX_ANALYSES_PER_RUN = 80  # caps Claude spend if a first run finds a big backlog
REDISCOVER_AFTER_DAYS = 7


def log(msg: str) -> None:
    print(msg, flush=True)


def resolve_feed(client, db: DB, company: dict) -> tuple[str, str] | None:
    """Which board to read for a company, using the cached discovery result when fresh."""
    if company["ats"] == "workday":
        return "workday", ""
    cached = db.get_feed(company["name"])
    if cached:
        age_days = (datetime.now(timezone.utc).replace(tzinfo=None) - datetime.fromisoformat(cached["checked_at"])).days
        if cached["ok"] or age_days < REDISCOVER_AFTER_DAYS:
            return (cached["ats"], cached["slug"]) if cached["ok"] else None
    found = ats.discover(client, company)
    if found:
        db.set_feed(company["name"], found[0], found[1], True)
    else:
        db.set_feed(company["name"], "", "", False, "no public board found")
    return found


def collect(settings, db: DB, stats: dict) -> None:
    prefs = settings.prefs
    with ats.make_client() as client:
        for company in settings.companies:
            if company["ats"] == "none" or filters.company_excluded(company["name"], prefs):
                continue
            stats["companies_scanned"] += 1
            try:
                feed = resolve_feed(client, db, company)
                if not feed:
                    stats["broken_feeds"].append(company["name"])
                    continue
                kind, slug = feed
                if kind == "workday":
                    postings = ats.workday(client, company["workday"]["host"], company["workday"]["site"])
                else:
                    postings = ats.FETCHERS[kind](client, slug)
            except (ats.FeedError, httpx.HTTPError, ValueError) as exc:
                log(f"  ! {company['name']}: {exc}")
                stats["broken_feeds"].append(company["name"])
                if company["ats"] == "auto":
                    db.set_feed(company["name"], "", "", False, str(exc)[:200])
                continue

            stats["postings_seen"] += len(postings)
            for p in postings:
                tier = filters.title_tier(p["title"], prefs)
                if not tier or not filters.location_ok(p["location"], p["workplace"], prefs):
                    continue
                job_id = f"{kind}:{company['name']}:{p['external_id']}"
                if db.get_job_status(job_id) is None:
                    try:
                        ats.fetch_details(client, p)
                    except (ats.FeedError, httpx.HTTPError, ValueError) as exc:
                        log(f"  ! details for {p['title']} at {company['name']}: {exc}")
                if db.upsert_job({**p, "id": job_id, "company": company["name"], "source": kind, "title_tier": tier}):
                    stats["new_candidates"] += 1
            log(f"  {company['name']}: {len(postings)} postings")
            db.commit()


def commute_for(job: dict, analysis: dict, company: dict | None, settings, db: DB, client) -> dict:
    """Shortest peak-hour commute to the office named in the post, else to the company's known offices."""
    prefs = settings.prefs
    if analysis.get("office_location"):
        destinations = [f"{analysis['office_location']}, Bengaluru"]
    else:
        destinations = list(company.get("offices", [])) if company else []
    destinations = [d for d in destinations if commute.is_specific(d)]
    best = None
    for dest in destinations:
        result = db.cached_commute(dest)
        if result is None:
            result = commute.check(client, settings.maps_api_key, settings.home_address, dest, prefs)
            if _fastest(result) != float("inf"):  # don't cache API failures
                db.cache_commute(dest, result)
        result = {**result, "verdict": commute.verdict(result, prefs)}
        if best is None or _fastest(result) < _fastest(best):
            best = result
    return best or {"verdict": "unknown"}


def _fastest(r: dict) -> float:
    vals = [r.get(k) for k in ("car", "bike", "metro") if r.get(k) is not None]
    return min(vals) if vals else float("inf")


def analyse(settings, db: DB, stats: dict) -> None:
    prefs = settings.prefs
    companies = {c["name"]: c for c in settings.companies}
    rejected: Counter = stats["rejected"]
    pending = db.jobs_with_status("new")[:MAX_ANALYSES_PER_RUN]
    with httpx.Client(timeout=30) as maps_client:
        for job in pending:
            def reject(reason: str, **extra):
                rejected[reason] += 1
                db.set_job(job["id"], status="rejected", reject_reason=reason, **extra)

            hint = filters.work_mode_hint(job["description"] or "", job["workplace"] or "")
            if hint == "office":
                reject("5-day office")
                continue
            try:
                a = scorer.analyse(job, settings.profile)
            except llm.LLMError as exc:
                log(f"  ! scoring {job['title']} at {job['company']}: {exc}")
                continue  # stays 'new', retried next run

            max_days = prefs["work_mode"]["max_office_days_per_week"]
            if a["work_mode"] == "office" or (a["office_days_per_week"] or 0) > max_days:
                reject("office days", analysis=a)
                continue
            if a["work_mode"] == "unknown" and not prefs["work_mode"]["keep_unknown"]:
                reject("work mode unknown", analysis=a)
                continue
            pay = scorer.pay_verdict(a, prefs)
            if pay == "too_low":
                reject("pay below floor", analysis=a)
                continue
            if job["title_tier"] == "secondary" and pay != "ok" and a["company_reputation"] < 4:
                reject("senior PM at weaker company", analysis=a)
                continue
            if a["fit_score"] < prefs["scoring"]["min_fit_score"]:
                reject("low fit", analysis=a)
                continue

            c = {"verdict": "remote"} if a["work_mode"] == "remote" else \
                commute_for(job, a, companies.get(job["company"]), settings, db, maps_client)
            if c["verdict"] == "too_far":
                reject("commute too long", analysis=a, commute=c)
                continue
            a["pay_verdict"] = pay
            db.set_job(job["id"], status="shortlisted", analysis=a, commute=c)
            log(f"  ✓ {job['title']} at {job['company']} (fit {a['fit_score']})")
            db.commit()


def deliver(settings, subject: str, html: str, text: str, dry_run: bool, name: str) -> None:
    if dry_run:
        out = ROOT / "out"
        out.mkdir(exist_ok=True)
        (out / f"{name}.html").write_text(html, encoding="utf-8")
        log(f"  wrote out/{name}.html — {subject}")
        return
    mailer.send(settings.gmail_address, settings.gmail_app_password, settings.email_to, subject, html, text)
    log(f"  sent: {subject}")


def run_jobs(settings, db: DB, dry_run: bool) -> None:
    stats = {"companies_scanned": 0, "postings_seen": 0, "new_candidates": 0,
             "broken_feeds": [], "rejected": Counter()}
    log("Collecting jobs…")
    collect(settings, db, stats)
    log("Scoring new jobs…")
    analyse(settings, db, stats)
    jobs = db.jobs_with_status("shortlisted")
    for j in jobs:
        j["pay_verdict"] = j["analysis"].get("pay_verdict", "")
    today = datetime.now(IST).strftime("%a %d %b %Y")
    deliver(settings, *emails.digest(jobs, stats, today), dry_run, "digest")
    if not dry_run:
        for j in jobs:
            db.set_job(j["id"], status="emailed", emailed_at=datetime.now(IST).isoformat())
    db.commit()


def run_prep(settings, db: DB, dry_run: bool) -> None:
    log("Writing today's prep…")
    now = datetime.now(IST)
    p = prep.generate(now.date(), settings.profile, settings.prefs, db.recent_prep_titles())
    deliver(settings, *emails.prep_email(p, now.strftime("%a %d %b")), dry_run, "prep")
    db.add_prep(now.date().isoformat(), p["topic"], p["title"])
    db.commit()


def check(settings, db: DB) -> int:
    missing = settings.missing()
    log("Missing settings: " + (", ".join(missing) if missing else "none"))
    log(f"Companies configured: {len(settings.companies)}")
    for feed in db.all_feeds():
        log(f"  {'ok ' if feed['ok'] else 'ERR'} {feed['company']}: {feed['ats']} {feed['slug']} {feed['note'] or ''}")
    return 1 if missing else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jobagent")
    parser.add_argument("command", choices=["run", "jobs", "prep", "check"])
    parser.add_argument("--dry-run", action="store_true", help="write emails to out/ instead of sending")
    args = parser.parse_args(argv)

    settings = load_settings()
    db = DB(Path(settings.db_path))
    if args.command == "check":
        return check(settings, db)
    missing = [m for m in settings.missing() if not (args.dry_run and m.startswith("GMAIL"))]
    if missing:
        log("Cannot run, missing: " + ", ".join(missing))
        return 1

    failures = 0
    if args.command in ("run", "jobs"):
        try:
            run_jobs(settings, db, args.dry_run)
        except Exception as exc:  # keep going so the prep email still arrives
            log(f"Job digest failed: {exc!r}")
            failures += 1
    if args.command in ("run", "prep"):
        try:
            run_prep(settings, db, args.dry_run)
        except Exception as exc:
            log(f"Prep email failed: {exc!r}")
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
