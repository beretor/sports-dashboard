"""
fetch_strava.py
---------------
Récupère les activités Strava des N derniers jours via l'API Strava.
Nécessite dans .env (ou GitHub Secrets) :
  STRAVA_CLIENT_ID
  STRAVA_CLIENT_SECRET
  STRAVA_REFRESH_TOKEN
"""

import os
import time
import requests
from datetime import datetime, timedelta, timezone


# ── Config ────────────────────────────────────────────────────────────────────
DAYS_BACK = 7
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE  = "https://www.strava.com/api/v3"

ACTIVITY_TYPE_ICONS = {
    "Run":       "🏃",
    "Ride":      "🚴",
    "Swim":      "🏊",
    "Hike":      "🥾",
    "Walk":      "🚶",
    "WeightTraining": "🏋️",
    "Workout":   "💪",
    "Yoga":      "🧘",
    "Soccer":    "⚽",
    "Tennis":    "🎾",
}


# ── Auth ──────────────────────────────────────────────────────────────────────
def _get_access_token() -> str:
    """Échange le refresh_token contre un access_token."""
    client_id     = os.environ["STRAVA_CLIENT_ID"]
    client_secret = os.environ["STRAVA_CLIENT_SECRET"]
    refresh_token = os.environ["STRAVA_REFRESH_TOKEN"]

    resp = requests.post(STRAVA_TOKEN_URL, data={
        "client_id":     client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type":    "refresh_token",
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()["access_token"]


# ── Formatters ────────────────────────────────────────────────────────────────
def _format_pace(speed_ms: float, activity_type: str) -> str:
    """Convertit m/s en allure (min/km) pour la course, km/h pour le vélo."""
    if speed_ms <= 0:
        return "—"
    if activity_type in ("Run", "Hike", "Walk"):
        pace_sec_per_km = 1000 / speed_ms
        mins = int(pace_sec_per_km // 60)
        secs = int(pace_sec_per_km % 60)
        return f"{mins}:{secs:02d}/km"
    else:
        return f"{speed_ms * 3.6:.1f} km/h"


def _format_duration(seconds: int) -> int:
    """Retourne la durée en minutes."""
    return round(seconds / 60)


# ── Main fetch ────────────────────────────────────────────────────────────────
def fetch_activities(days: int = DAYS_BACK) -> dict:
    """
    Retourne un dict prêt à être injecté dans data.json section 'strava'.
    """
    token  = _get_access_token()
    headers = {"Authorization": f"Bearer {token}"}

    # Timestamp UNIX de début (il y a N jours)
    after_ts = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())

    # Récupère toutes les activités (pagination simple, max 200)
    resp = requests.get(
        f"{STRAVA_API_BASE}/athlete/activities",
        headers=headers,
        params={"after": after_ts, "per_page": 50, "page": 1},
        timeout=30,
    )
    resp.raise_for_status()
    raw_activities = resp.json()

    # Récupère le profil athlète (pour le prénom)
    athlete_resp = requests.get(
        f"{STRAVA_API_BASE}/athlete",
        headers=headers,
        timeout=10,
    )
    athlete_name = "Athlète"
    if athlete_resp.ok:
        a = athlete_resp.json()
        athlete_name = a.get("firstname", "Athlète")

    # ── Transforme les activités ──
    activities = []
    total_distance_m   = 0
    total_duration_s   = 0
    total_elevation_m  = 0

    for act in raw_activities:
        act_type    = act.get("sport_type") or act.get("type", "Workout")
        distance_km = round(act.get("distance", 0) / 1000, 2)
        duration_min = _format_duration(act.get("elapsed_time", 0))
        speed_ms    = act.get("average_speed", 0)
        avg_hr      = act.get("average_heartrate")
        elevation_m = round(act.get("total_elevation_gain", 0))

        # Date ISO (Strava renvoie "2026-04-07T06:30:00Z")
        start_date  = act.get("start_date", "")[:10]  # garde "YYYY-MM-DD"

        activities.append({
            "date":        start_date,
            "type":        act_type,
            "name":        act.get("name", "Activité"),
            "distance_km": distance_km,
            "duration_min": duration_min,
            "pace":        _format_pace(speed_ms, act_type),
            "avg_hr":      int(avg_hr) if avg_hr else None,
            "elevation_m": elevation_m,
        })

        total_distance_m  += act.get("distance", 0)
        total_duration_s  += act.get("elapsed_time", 0)
        total_elevation_m += act.get("total_elevation_gain", 0)

    # Trie par date décroissante
    activities.sort(key=lambda x: x["date"], reverse=True)

    return {
        "athlete":     athlete_name,
        "period_days": days,
        "summary_ai":  "",   # rempli par analyze.py
        "stats": {
            "total_activities":  len(activities),
            "total_distance_km": round(total_distance_m / 1000, 1),
            "total_duration_min": _format_duration(total_duration_s),
            "total_elevation_m": round(total_elevation_m),
        },
        "activities": activities,
    }


if __name__ == "__main__":
    import json
    data = fetch_activities()
    print(json.dumps(data, indent=2, ensure_ascii=False))
