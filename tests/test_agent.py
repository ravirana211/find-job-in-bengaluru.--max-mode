import json
from collections import Counter

import httpx
import yaml

from jobagent import commute, emails, filters, scorer
from jobagent.config import CONFIG_DIR
from jobagent.sources import ats

PREFS = yaml.safe_load((CONFIG_DIR / "preferences.yaml").read_text())


def test_title_tiers():
    assert filters.title_tier("Director of Product, Payments", PREFS) == "primary"
    assert filters.title_tier("VP Product", PREFS) == "primary"
    assert filters.title_tier("Group Product Manager - Growth", PREFS) == "primary"
    assert filters.title_tier("Senior Product Manager", PREFS) == "secondary"
    assert filters.title_tier("Product Marketing Director", PREFS) is None
    assert filters.title_tier("Senior Program Manager", PREFS) is None
    assert filters.title_tier("Software Engineer", PREFS) is None


def test_location():
    assert filters.location_ok("Bengaluru, Karnataka, India", "", PREFS)
    assert filters.location_ok("Bangalore", "", PREFS)
    assert filters.location_ok("Remote - India", "remote", PREFS)
    assert not filters.location_ok("Remote - US", "remote", PREFS)
    assert not filters.location_ok("Gurugram", "", PREFS)


def test_company_exclusion():
    assert filters.company_excluded("Xoxoday", PREFS)
    assert not filters.company_excluded("Razorpay", PREFS)


def test_work_mode_hint():
    assert filters.work_mode_hint("You will work from office 5 days a week") == "office"
    assert filters.work_mode_hint("Hybrid: 3 days a week in our Koramangala office") == "hybrid"
    assert filters.work_mode_hint("This is a fully remote role") == "remote"
    assert filters.work_mode_hint("Great team") == "unknown"
    assert filters.work_mode_hint("", "hybrid") == "hybrid"


def test_commute_verdict():
    assert commute.verdict({"car": 35, "bike": 30, "metro": 70}, PREFS) == "ok"
    assert commute.verdict({"car": 55, "bike": 45, "metro": 55}, PREFS) == "ok"
    assert commute.verdict({"car": 55, "bike": 45, "metro": 75}, PREFS) == "too_far"
    assert commute.verdict({"car": None, "bike": None, "metro": None}, PREFS) == "unknown"
    assert not commute.is_specific("Bengaluru")
    assert commute.is_specific("Koramangala, Bengaluru")


def _analysis(**kw):
    base = dict(level="Director", fit_score=80, work_mode="hybrid", office_days_per_week=3,
                office_location="", stated_ctc_lpa=None, estimated_ctc_lpa_low=55,
                estimated_ctc_lpa_high=75, salary_confidence="medium", company_reputation=4,
                why_fit=["GenAI B2B SaaS"], gaps=[], pitch="AI agents in enterprise sales",
                summary="Lead payments product")
    base.update(kw)
    return base


def test_pay_verdict():
    assert scorer.pay_verdict(_analysis(), PREFS) == "ok"
    assert scorer.pay_verdict(_analysis(stated_ctc_lpa=45), PREFS) == "too_low"
    assert scorer.pay_verdict(_analysis(estimated_ctc_lpa_high=50), PREFS) == "too_low"
    low_conf = _analysis(estimated_ctc_lpa_high=50, salary_confidence="low", company_reputation=5)
    assert scorer.pay_verdict(low_conf, PREFS) == "unknown_ok"


def _mock_client(routes: dict) -> httpx.Client:
    def handler(request: httpx.Request):
        for prefix, body in routes.items():
            if str(request.url).startswith(prefix):
                return httpx.Response(200, json=body)
        return httpx.Response(404, json={})
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_greenhouse_and_discovery():
    gh = {"jobs": [{"id": 1, "title": "Director, Product", "location": {"name": "Bengaluru"},
                    "absolute_url": "https://x/1", "content": "&lt;p&gt;Hybrid &amp;amp; fun&lt;/p&gt;"}]}
    client = _mock_client({"https://boards-api.greenhouse.io/v1/boards/razorpay/": gh})
    found = ats.discover(client, {"name": "Razorpay", "ats": "auto", "slugs": ["nope", "razorpay"]})
    assert found == ("greenhouse", "razorpay")
    jobs = ats.greenhouse(client, "razorpay")
    assert jobs[0]["description"] == "Hybrid & fun"


def test_discovery_rejects_foreign_board():
    lever = [{"id": "a", "text": "PM", "categories": {"location": "San Francisco"}, "hostedUrl": "u"}]
    client = _mock_client({"https://api.lever.co/v0/postings/jupiter": lever})
    assert ats.discover(client, {"name": "Jupiter", "ats": "auto"}) is None


def test_workday_list_and_details():
    host, site = "acme.wd5.myworkdayjobs.com", "Ext"
    base = f"https://{host}/wday/cxs/acme/{site}"
    client = _mock_client({
        f"{base}/jobs": {"total": 1, "jobPostings": [
            {"title": "Director Product", "externalPath": "/job/Bangalore/Dir_R123", "locationsText": "Bangalore"}]},
        f"{base}/job/": {"jobPostingInfo": {"jobDescription": "<p>Hybrid role</p>", "location": "Bangalore"}},
    })
    jobs = ats.workday(client, host, site)
    assert jobs[0]["external_id"] == "R123"
    ats.fetch_details(client, jobs[0])
    assert jobs[0]["description"] == "Hybrid role"


def test_digest_renders():
    job = {"title": "Director of Product", "company": "Razorpay", "url": "https://x",
           "analysis": _analysis(), "commute": {"car": 25, "bike": 20, "metro": 35, "destination": "Adugodi"},
           "pay_verdict": "ok"}
    subject, html, text = emails.digest([job], {"rejected": Counter({"low fit": 2})}, "Mon 02 Nov 2026")
    assert "1 new Product role" in subject
    assert "Razorpay" in html and "25 min" in html and "low fit: 2" in html


def test_pipeline_dry_run(tmp_path, monkeypatch):
    """End to end with all network calls mocked."""
    from jobagent import __main__ as main_mod
    from jobagent.config import load_settings
    from jobagent.db import DB

    settings = load_settings()
    settings.companies = [{"name": "Razorpay", "ats": "greenhouse", "slugs": ["razorpay"],
                           "offices": ["SJR Cyber, Adugodi, Bengaluru"]}]
    settings.home_address = "Home"
    settings.profile = "Product leader"
    settings.maps_api_key = "k"
    db = DB(tmp_path / "t.sqlite")

    gh = {"jobs": [
        {"id": 1, "title": "Director of Product", "location": {"name": "Bengaluru"},
         "absolute_url": "https://x/1", "content": "Hybrid, 2 days a week"},
        {"id": 2, "title": "Head of Product", "location": {"name": "Bengaluru"},
         "absolute_url": "https://x/2", "content": "Work from office 5 days a week"},
        {"id": 3, "title": "Software Engineer", "location": {"name": "Bengaluru"},
         "absolute_url": "https://x/3", "content": ""},
    ]}
    monkeypatch.setattr(ats, "make_client", lambda: _mock_client({"https://boards-api.greenhouse.io/": gh}))
    monkeypatch.setattr(scorer, "analyse", lambda job, profile: _analysis())
    monkeypatch.setattr(commute, "check", lambda *a, **k: {"destination": "SJR Cyber", "car": 25, "bike": 20, "metro": 40})
    monkeypatch.setattr(main_mod, "ROOT", tmp_path)

    main_mod.run_jobs(settings, db, dry_run=True)
    html = (tmp_path / "out" / "digest.html").read_text()
    assert "Director of Product" in html
    assert "Head of Product" not in html  # 5-day office
    assert "Software Engineer" not in html
    statuses = {r["title"]: r["status"] for r in db.conn.execute("SELECT title, status FROM jobs")}
    assert statuses == {"Director of Product": "shortlisted", "Head of Product": "rejected"}
