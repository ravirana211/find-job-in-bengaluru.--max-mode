# find-job-in-bengaluru.--max-mode

A personal job agent that finds senior Product roles (Senior PM to VP) in Bengaluru that are
hybrid or remote, pay at least ₹60 LPA, and sit within a short commute of home. It emails a
daily digest at about 9 AM, plus a daily 30-minute interview-prep exercise.

See [PLAN.md](PLAN.md) for the full roadmap (outreach, referrals, applications, interview coaching).

## What it does each morning

1. Reads the public job boards of ~50 target companies (`config/companies.yaml`).
2. Keeps titles like Director / Head of / VP / Group / Principal Product, in Bengaluru or remote-India.
3. Drops jobs that need more than 3 office days a week.
4. Asks Claude to read each remaining job: fit for you, real seniority, likely pay, company reputation.
5. Drops jobs below ₹60 LPA (unknown pay is kept only for well-rated companies).
6. Checks the morning peak-hour commute from home by car, bike and metro (Google Maps).
   Keeps jobs within 40 min by road or 60 min by metro.
7. Emails the digest, then a separate prep email (case study, metrics, strategy, AI product,
   leadership story, company interview guide or rapid-fire Q&A, depending on the day).

## One-time setup (about 20 minutes, no coding)

### 1. Create three keys

| Key | Where |
|---|---|
| Claude API key | [console.anthropic.com](https://console.anthropic.com) → API keys → Create key |
| Google Maps key | [console.cloud.google.com](https://console.cloud.google.com) → create a project → APIs & Services → enable **Routes API** → Credentials → Create API key (restrict it to the Routes API) |
| Gmail app password | Turn on 2-Step Verification for your Google account, then [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) → create one named "job agent" |

### 2. Add them as repository secrets

GitHub repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**.
Add each of these (name exactly as shown):

| Secret name | Value |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API key |
| `GOOGLE_MAPS_API_KEY` | Google Maps key |
| `GMAIL_ADDRESS` | The Gmail address that sends the emails |
| `GMAIL_APP_PASSWORD` | The 16-character app password |
| `EMAIL_TO` | Where to receive the emails (optional; defaults to `GMAIL_ADDRESS`) |
| `HOME_ADDRESS` | Your full home address |
| `CANDIDATE_PROFILE` | Your profile summary (provided separately; never committed) |

Secrets are encrypted and never appear in the code or logs.

### 3. Run it

GitHub repo → **Actions** → **Daily job digest and prep** → **Run workflow**.
After that it runs by itself every morning.

## Changing preferences

Edit `config/preferences.yaml` (titles, pay floor, commute limits, excluded companies) or
`config/companies.yaml` (add a company and its Bengaluru office area).

## For developers

```bash
pip install -r requirements.txt
python -m pytest -q tests
python -m jobagent check           # missing settings and board health
python -m jobagent run --dry-run   # writes emails to out/ instead of sending
```
