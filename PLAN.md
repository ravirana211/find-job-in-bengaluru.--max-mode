# Project Plan: Bengaluru Senior/VP Product Job Agent

> Personal data (resume, phone, home location, LinkedIn connections, API keys) is never
> committed to this repo. It lives in GitHub Secrets / a private config only.

## Goal
Find hybrid/remote Senior-to-VP Product roles in Bengaluru that pay ≥ 60 LPA CTC (fixed + bonus, ESOPs excluded)
and are within commute range of home. Reach the hiring team or a referrer, apply, and prepare for and close the interview,
over a 6–8 month runway.

## Hard filters
| Filter | Rule |
|---|---|
| Titles | Primary: Director / Sr Director / Head of Product / AVP / VP Product, Group PM, Principal PM, Lead PM. Secondary (only if strong company/pay): Senior PM |
| Work mode | Hybrid with ≤ 3 office days/week, or remote. Drop 5-day-office roles. Unknown → keep, flag "verify" |
| Commute | ≤ 40 min by car/bike at weekday peak (9:30 AM, 6:30 PM) **or** ≤ 60 min by metro. Every office campus checked |
| Pay | ≥ 60 LPA CTC. Unknown pay → keep only if company is well-known and rated a good place to work, and show an estimated band |
| Exclusions | Current employer, its group companies, and its key clients/partners (confidentiality) |

Domain, company stage and size: no restriction.

## Architecture
Email-only for now. Runs on a schedule; no always-on server needed.

```
Sources ──► Collector ──► Filter (title, mode, commute, pay) ──► Scorer (Claude) ──► DB
                                                                                      │
   Daily email digest ◄── Digest builder ◄──────────────────────────────────────────────┤
   Outreach emails (Gmail API, approved templates, daily cap) ◄── Connector ◄─────────┤
   Prep email (case study / Q&A / peer guide) ◄── Prep Coach ◄─────────────────────────┘
```

**Job sources (all legitimate, no LinkedIn scraping):**
1. Public ATS feeds from a curated list of 200–300 Bengaluru product employers: Greenhouse, Lever, Ashby, SmartRecruiters, Workday.
2. Job-alert emails from LinkedIn, Naukri, iimjobs, Instahyre and Hirist, collected in a Gmail label and parsed.
3. A Google Jobs API (SerpAPI or similar) to fill gaps.

**Services:** Claude API (parsing, scoring, writing, coaching), Google Maps Routes API (peak-hour commute),
Gmail API (read alerts, send digest and outreach), Apollo/Hunter free tier (work-email lookup).

**Runtime:** GitHub Actions cron (recommended; free, runs with the laptop off) or a laptop scheduler.
SQLite database kept between runs.

## Phases
| # | Deliverable | Target |
|---|---|---|
| 0 | Profile + preferences config, company + office-address list, API keys in secrets | Week 1 |
| 1 | Job Hunter + daily digest email | Week 1–2 |
| 5a | Daily prep email (30 min/day): case study, Q&A, peer interview guide; MNC/GCC + Razorpay-style focus | Week 2 (early, prep starts now) |
| 2 | Application tracker in Google Sheet + follow-up reminders by email | Week 3 |
| 3 | Connector: LinkedIn connections → referrers; hiring manager/recruiter lookup; outreach drafts | Week 3–4 |
| 3b | Auto-send outreach with approved templates (daily cap, exclusion list, bounce check) | Week 4 |
| 4 | Apply Assistant: tailored resume + cover note + application answers per job | Week 4–5 |
| 6 | Interview Closer: company research pack, mock interviews, debrief, follow-ups, offer negotiation | Week 5–6 |

## Safety rules for outreach
- Send only from the personal Gmail, never to current-employer domains, group companies or clients.
- Only templates the user approved; ≤ 10–15 new cold emails/day; stop on bounce or reply.
- No automated LinkedIn actions.
- Every send logged in the tracker; a weekly summary of all outreach.
