"""SQLite store for jobs, commute cache, discovered feeds and prep history."""

import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,           -- source:company:external id
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    location TEXT,
    url TEXT,
    description TEXT,
    source TEXT,
    workplace TEXT,                -- work-mode field from the job board, if any
    title_tier TEXT,               -- primary | secondary
    first_seen TEXT DEFAULT (datetime('now')),
    last_seen TEXT DEFAULT (datetime('now')),
    status TEXT DEFAULT 'new',     -- new | rejected | shortlisted | emailed
    reject_reason TEXT,
    analysis TEXT,                 -- JSON from the scorer
    commute TEXT,                  -- JSON from the commute check
    emailed_at TEXT
);
CREATE TABLE IF NOT EXISTS commute_cache (
    destination TEXT PRIMARY KEY,
    result TEXT,
    checked_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS feeds (
    company TEXT PRIMARY KEY,
    ats TEXT,
    slug TEXT,
    ok INTEGER,
    note TEXT,
    checked_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS prep_history (
    day TEXT PRIMARY KEY,
    topic TEXT,
    title TEXT
);
"""


class DB:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def upsert_job(self, job: dict) -> bool:
        """Insert a job or refresh last_seen. Returns True when the job is new."""
        cur = self.conn.execute("SELECT 1 FROM jobs WHERE id = ?", (job["id"],))
        if cur.fetchone():
            self.conn.execute("UPDATE jobs SET last_seen = datetime('now') WHERE id = ?", (job["id"],))
            return False
        self.conn.execute(
            "INSERT INTO jobs (id, company, title, location, url, description, source, workplace, title_tier)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (job["id"], job["company"], job["title"], job.get("location", ""), job.get("url", ""),
             job.get("description", ""), job.get("source", ""), job.get("workplace", ""), job.get("title_tier", "")),
        )
        return True

    def get_job_status(self, job_id: str) -> str | None:
        row = self.conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return row["status"] if row else None

    def set_job(self, job_id: str, **fields) -> None:
        for key in ("analysis", "commute"):
            if key in fields and not isinstance(fields[key], str):
                fields[key] = json.dumps(fields[key])
        cols = ", ".join(f"{k} = ?" for k in fields)
        self.conn.execute(f"UPDATE jobs SET {cols} WHERE id = ?", (*fields.values(), job_id))

    def jobs_with_status(self, status: str) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM jobs WHERE status = ?", (status,)).fetchall()
        out = []
        for row in rows:
            job = dict(row)
            for key in ("analysis", "commute"):
                job[key] = json.loads(job[key]) if job[key] else None
            out.append(job)
        return out

    def get_feed(self, company: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM feeds WHERE company = ?", (company,)).fetchone()
        return dict(row) if row else None

    def set_feed(self, company: str, ats: str, slug: str, ok: bool, note: str = "") -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO feeds (company, ats, slug, ok, note, checked_at) VALUES (?, ?, ?, ?, ?, datetime('now'))",
            (company, ats, slug, int(ok), note),
        )

    def all_feeds(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM feeds ORDER BY company")]

    def cached_commute(self, destination: str, max_age_days: int = 30) -> dict | None:
        row = self.conn.execute(
            "SELECT result FROM commute_cache WHERE destination = ? AND checked_at > datetime('now', ?)",
            (destination, f"-{max_age_days} days"),
        ).fetchone()
        return json.loads(row["result"]) if row else None

    def cache_commute(self, destination: str, result: dict) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO commute_cache (destination, result, checked_at) VALUES (?, ?, datetime('now'))",
            (destination, json.dumps(result)),
        )

    def recent_prep_titles(self, limit: int = 60) -> list[str]:
        rows = self.conn.execute("SELECT title FROM prep_history ORDER BY day DESC LIMIT ?", (limit,))
        return [r["title"] for r in rows]

    def add_prep(self, day: str, topic: str, title: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO prep_history (day, topic, title) VALUES (?, ?, ?)", (day, topic, title))

    def counts_by_status(self) -> dict:
        rows = self.conn.execute("SELECT status, COUNT(*) AS n FROM jobs GROUP BY status")
        return {r["status"]: r["n"] for r in rows}

    def commit(self) -> None:
        self.conn.commit()
