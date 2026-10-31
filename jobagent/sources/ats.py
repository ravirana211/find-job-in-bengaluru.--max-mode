"""Public job-board feeds: Greenhouse, Lever, Ashby, SmartRecruiters and Workday.

Each fetcher returns a list of postings:
    {"external_id", "title", "location", "url", "description", "workplace"}
`description` may be empty for boards whose list endpoint has no body; call
`fetch_details` for the postings that survive the title/location filter.
"""

import html
import re

import httpx

TIMEOUT = httpx.Timeout(30.0)
HEADERS = {"User-Agent": "Mozilla/5.0 (job-search assistant; personal use)"}
INDIA_HINTS = ("india", "bengaluru", "bangalore", "karnataka")


class FeedError(Exception):
    pass


def html_to_text(raw: str) -> str:
    text = html.unescape(raw or "")
    text = re.sub(r"<(br|/p|/li|/h\d|/div)[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<li[^>]*>", "• ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t\xa0]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def _get_json(client: httpx.Client, url: str, **kwargs):
    resp = client.get(url, **kwargs)
    if resp.status_code != 200:
        raise FeedError(f"HTTP {resp.status_code}")
    return resp.json()


def greenhouse(client: httpx.Client, slug: str) -> list[dict]:
    data = _get_json(client, f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", params={"content": "true"})
    return [
        {
            "external_id": str(j["id"]),
            "title": j.get("title", ""),
            "location": (j.get("location") or {}).get("name", ""),
            "url": j.get("absolute_url", ""),
            "description": html_to_text(j.get("content", "")),
            "workplace": "",
        }
        for j in data.get("jobs", [])
    ]


def lever(client: httpx.Client, slug: str) -> list[dict]:
    data = _get_json(client, f"https://api.lever.co/v0/postings/{slug}", params={"mode": "json"})
    if not isinstance(data, list):
        raise FeedError("unexpected response")
    out = []
    for j in data:
        cats = j.get("categories") or {}
        sections = "\n\n".join(
            f"{s.get('text', '')}\n{html_to_text(s.get('content', ''))}" for s in j.get("lists", [])
        )
        desc = "\n\n".join(filter(None, [j.get("descriptionPlain", ""), sections, j.get("additionalPlain", "")]))
        out.append({
            "external_id": j["id"],
            "title": j.get("text", ""),
            "location": ", ".join(cats.get("allLocations") or [cats.get("location", "")]),
            "url": j.get("hostedUrl", ""),
            "description": desc,
            "workplace": j.get("workplaceType", ""),
        })
    return out


def ashby(client: httpx.Client, slug: str) -> list[dict]:
    data = _get_json(client, f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
                     params={"includeCompensation": "true"})
    out = []
    for j in data.get("jobs", []):
        locations = [j.get("location", "")] + [
            s.get("location", "") for s in j.get("secondaryLocations", []) or []
        ]
        comp = (j.get("compensation") or {}).get("compensationTierSummary", "")
        desc = j.get("descriptionPlain", "") + (f"\n\nCompensation: {comp}" if comp else "")
        out.append({
            "external_id": j.get("id", j.get("jobUrl", "")),
            "title": j.get("title", ""),
            "location": ", ".join(filter(None, locations)),
            "url": j.get("jobUrl", ""),
            "description": desc,
            "workplace": j.get("workplaceType", "") or ("remote" if j.get("isRemote") else ""),
        })
    return out


def smartrecruiters(client: httpx.Client, slug: str) -> list[dict]:
    out, offset = [], 0
    while True:
        data = _get_json(client, f"https://api.smartrecruiters.com/v1/companies/{slug}/postings",
                         params={"q": "product", "limit": 100, "offset": offset})
        for j in data.get("content", []):
            loc = j.get("location") or {}
            out.append({
                "external_id": j["id"],
                "title": j.get("name", ""),
                "location": ", ".join(filter(None, [loc.get("city"), loc.get("region"), loc.get("country")]))
                + (" (remote)" if loc.get("remote") else ""),
                "url": f"https://jobs.smartrecruiters.com/{slug}/{j['id']}",
                "description": "",
                "workplace": "remote" if loc.get("remote") else "",
                "_detail": f"https://api.smartrecruiters.com/v1/companies/{slug}/postings/{j['id']}",
            })
        offset += 100
        if offset >= data.get("totalFound", 0) or offset >= 500:
            return out


def workday(client: httpx.Client, host: str, site: str) -> list[dict]:
    tenant = host.split(".")[0]
    base = f"https://{host}/wday/cxs/{tenant}/{site}"
    out, offset = [], 0
    while True:
        resp = client.post(f"{base}/jobs", json={
            "appliedFacets": {}, "limit": 20, "offset": offset, "searchText": "product manager India",
        })
        if resp.status_code != 200:
            raise FeedError(f"HTTP {resp.status_code}")
        data = resp.json()
        postings = data.get("jobPostings", [])
        for j in postings:
            path = j.get("externalPath", "")
            out.append({
                "external_id": path.rsplit("_", 1)[-1] or path,
                "title": j.get("title", ""),
                "location": j.get("locationsText", ""),
                "url": f"https://{host}/en-US/{site}{path}",
                "description": "",
                "workplace": "",
                "_detail": f"{base}{path}",
            })
        offset += 20
        if not postings or offset >= min(data.get("total", 0), 200):
            return out


def fetch_details(client: httpx.Client, posting: dict) -> None:
    """Fill in description (and a better location) for list-only boards."""
    url = posting.pop("_detail", None)
    if not url or posting.get("description"):
        return
    data = _get_json(client, url)
    if "jobPostingInfo" in data:  # Workday
        info = data["jobPostingInfo"]
        posting["description"] = html_to_text(info.get("jobDescription", ""))
        extra = info.get("additionalLocations") or []
        posting["location"] = ", ".join(filter(None, [info.get("location", posting["location"]), *extra]))
        posting["workplace"] = info.get("remoteType", "") or posting["workplace"]
    else:  # SmartRecruiters
        sections = (data.get("jobAd") or {}).get("sections") or {}
        posting["description"] = "\n\n".join(
            html_to_text((sections.get(k) or {}).get("text", ""))
            for k in ("companyDescription", "jobDescription", "qualifications", "additionalInformation")
        ).strip()


FETCHERS = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby, "smartrecruiters": smartrecruiters}


def slug_candidates(company: dict) -> list[str]:
    if company.get("slugs"):
        return list(company["slugs"])
    name = company["name"].lower()
    words = re.findall(r"[a-z0-9]+", name)
    return list(dict.fromkeys(["".join(words), "-".join(words), words[0]]))


def looks_like_india_board(postings: list[dict]) -> bool:
    """Guards against a generic slug matching an unrelated company abroad."""
    return any(any(h in p["location"].lower() for h in INDIA_HINTS) for p in postings)


def discover(client: httpx.Client, company: dict) -> tuple[str, str] | None:
    """Find which board and slug a company uses. Returns (ats, slug) or None."""
    ats_order = [company["ats"]] if company["ats"] in FETCHERS else list(FETCHERS)
    for ats in ats_order:
        for slug in slug_candidates(company):
            try:
                postings = FETCHERS[ats](client, slug)
            except (FeedError, httpx.HTTPError, ValueError):
                continue
            if postings and (company["ats"] != "auto" or looks_like_india_board(postings)):
                return ats, slug
    return None


def make_client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True)
