"""Peak-hour commute checks with the Google Maps Routes API."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
IST = ZoneInfo("Asia/Kolkata")
MODES = {"car": "DRIVE", "bike": "TWO_WHEELER", "metro": "TRANSIT"}


def next_weekday_departure(hhmm: str, now: datetime | None = None) -> datetime:
    now = now or datetime.now(IST)
    hour, minute = map(int, hhmm.split(":"))
    day = now + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day.replace(hour=hour, minute=minute, second=0, microsecond=0)


def is_specific(address: str) -> bool:
    """'Bengaluru' alone is too vague to time a commute against."""
    parts = [p.strip().lower() for p in address.split(",") if p.strip()]
    return len([p for p in parts if p not in ("bengaluru", "bangalore", "karnataka", "india")]) > 0


def _route_minutes(client: httpx.Client, api_key: str, origin: str, destination: str,
                   mode: str, departure: datetime) -> int | None:
    body = {
        "origin": {"address": origin},
        "destination": {"address": destination},
        "travelMode": mode,
        "departureTime": departure.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "regionCode": "IN",
    }
    if mode in ("DRIVE", "TWO_WHEELER"):
        body["routingPreference"] = "TRAFFIC_AWARE"
    resp = client.post(ROUTES_URL, json=body, headers={
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "routes.duration,routes.distanceMeters",
    })
    if resp.status_code != 200:
        raise RuntimeError(f"Routes API {resp.status_code}: {resp.text[:200]}")
    routes = resp.json().get("routes") or []
    if not routes:
        return None
    return round(int(routes[0]["duration"].rstrip("s")) / 60)


def check(client: httpx.Client, api_key: str, home: str, destination: str, prefs: dict) -> dict:
    """Minutes by car, bike and metro at morning peak, and whether it fits the limits."""
    departure = next_weekday_departure(prefs["commute"]["peak_departure_local"])
    minutes = {}
    for name, mode in MODES.items():
        try:
            minutes[name] = _route_minutes(client, api_key, home, destination, mode, departure)
        except (RuntimeError, httpx.HTTPError, KeyError, ValueError) as exc:
            minutes[name] = None
            minutes[f"{name}_error"] = str(exc)[:200]
    return {"destination": destination, **minutes}


def verdict(result: dict, prefs: dict) -> str:
    """'ok', 'too_far' or 'unknown'."""
    road = [m for m in (result.get("car"), result.get("bike")) if m is not None]
    metro = result.get("metro")
    if not road and metro is None:
        return "unknown"
    if (road and min(road) <= prefs["commute"]["max_minutes_car_or_bike"]) or (
        metro is not None and metro <= prefs["commute"]["max_minutes_metro"]
    ):
        return "ok"
    return "too_far"
