"""Loads search preferences, the company list and private settings.

Private settings (home address, profile, keys) come from environment variables,
which GitHub Actions fills from repository secrets. For local runs they can also
live in files under private/ (git-ignored).
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
PRIVATE_DIR = ROOT / "private"
DATA_DIR = ROOT / "data"


def _private(env_name: str, file_name: str | None = None) -> str:
    value = os.environ.get(env_name, "").strip()
    if not value and file_name:
        path = PRIVATE_DIR / file_name
        if path.exists():
            value = path.read_text(encoding="utf-8").strip()
    return value


@dataclass
class Settings:
    prefs: dict
    companies: list[dict]
    home_address: str
    profile: str
    gmail_address: str
    gmail_app_password: str
    email_to: str
    maps_api_key: str
    db_path: Path = field(default_factory=lambda: DATA_DIR / "jobagent.sqlite")

    def missing(self) -> list[str]:
        required = {
            "HOME_ADDRESS": self.home_address,
            "CANDIDATE_PROFILE": self.profile,
            "GMAIL_ADDRESS": self.gmail_address,
            "GMAIL_APP_PASSWORD": self.gmail_app_password,
            "GOOGLE_MAPS_API_KEY": self.maps_api_key,
            "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY", ""),
        }
        return [name for name, value in required.items() if not value]


def load_settings() -> Settings:
    prefs = yaml.safe_load((CONFIG_DIR / "preferences.yaml").read_text(encoding="utf-8"))
    companies = yaml.safe_load((CONFIG_DIR / "companies.yaml").read_text(encoding="utf-8"))["companies"]
    gmail = _private("GMAIL_ADDRESS")
    return Settings(
        prefs=prefs,
        companies=companies,
        home_address=_private("HOME_ADDRESS", "home_address.txt"),
        profile=_private("CANDIDATE_PROFILE", "profile.md"),
        gmail_address=gmail,
        gmail_app_password=_private("GMAIL_APP_PASSWORD"),
        email_to=_private("EMAIL_TO") or gmail,
        maps_api_key=_private("GOOGLE_MAPS_API_KEY"),
    )
