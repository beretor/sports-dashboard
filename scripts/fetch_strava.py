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
import requests
from datetime import datetime, timedelta, timezone


# ── Config ────────────────────────────────────────────────────────────────────
DAYS_BACK = 30
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE  = "https://www.strava.com/api/v3"


# ── Auth ──────────────────────────────────────────────────────────────────────
def _get_access_token() -> str:
    resp = requests.post(STRAVA_TOKEN_URL, data={
        "client_id":     os.environ["STRAVA_CLIENT_ID"],
        "client_secret": os.environ["STRAVA_CLIENT_SECRET"],
        "refresh_token": os.environ["STRAVA_REFRESH_TOKEN"],
        "grant_type":    "refresh_token",
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()["access_token"]


# ── Formatters ────────────────────────────────────────────────────────────────
def _format_pace(speed_ms: float, activity_type: str) -> str:
    if speed_ms <= 0:
        return "—"
    if activity_type in ("Run", "Hike", "Walk", "TrailRun"):
        pace_sec = 1000 / speed_ms
        return f"{int(pace_sec // 60)}:{int(pace_sec % 60):02d}/km"
    else:
        return f"{speed_ms * 3.6:.1f} km/h"


def _format_duration(seconds: int) -> int:
    return round(seconds / 60)


def _hms(seconds: int) -> str:
    """Retourne HH:MM:SS ou MM:SS."""
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


# ── Weekly aggregation ────────────────────────────────────────────────────────
def _build_weekly_stats(activities: list, days: int) -> list:
    """
    Agrège les activités par semaine (lundi→dimanche).
    Retourne les N dernières semaines complètes + semaine en cours.
    """
    from collections import defaultdict
    weeks = defaultdict(lambda: {"distance_km": 0, "duration_min": 0,
                                  "count": 0, "elevation_m": 0})
    for act in activities:
        d = datetime.fromisoformat(act["date"])
        # Lundi de la semaine
        monday = (d - timedelta(days=d.weekday())).strftime("%Y-%m-%d")
        weeks[monday]["distance_km"]  += act["distance_km"]
        weeks[monday]["duration_min"] += act["duration_min"]
        weeks[monday]["elevation_m"]  += act["elevation_m"]
        weeks[monday]["count"]        += 1

    # Trie par date et arrondit
    result = []
    for monday in sorted(weeks.keys()):
        w = weeks[monday]
        result.append({
            "week_start":   monday,
            "distance_km":  round(w["distance_km"], 1),
            "duration_min": round(w["duration_min"]),
            "elevation_m":  round(w["elevation_m"]),
            "count":        w["count"],
        })
    return result


# ── Main fetch ────────────────────────────────────────────────────────────────
def fetch_activities(days: int = DAYS_BACK) -> dict:
    token   = _get_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    after_ts = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())

    # Liste des activités
    raw = requests.get(
        f"{STRAVA_API_BASE}/athlete/activities",
        headers=headers,
        params={"after": after_ts, "per_page": 100, "page": 1},
        timeout=30,
    )
    raw.raise_for_status()
    raw_activities = raw.json()

    # Profil athlète
    athlete_resp = requests.get(f"{STRAVA_API_BASE}/athlete", headers=headers, timeout=10)
    athlete_name = "Athlète"
    if athlete_resp.ok:
        a = athlete_resp.json()
        athlete_name = a.get("firstname", "Athlète")

    # ── Transforme chaque activité ──
    activities = []
    total_distance_m  = 0
    total_duration_s  = 0
    total_elevation_m = 0

    for act in raw_activities:
        act_type     = act.get("sport_type") or act.get("type", "Workout")
        distance_km  = round(act.get("distance", 0) / 1000, 2)
        elapsed_s    = act.get("elapsed_time", 0)
        moving_s     = act.get("moving_time", elapsed_s)
        speed_ms     = act.get("average_speed", 0)
        avg_hr       = act.get("average_heartrate")
        max_hr       = act.get("max_heartrate")
        elevation_m  = round(act.get("total_elevation_gain", 0))
        calories     = act.get("kilojoules") or act.get("calories")
        avg_cadence  = act.get("average_cadence")
        avg_watts    = act.get("average_watts")
        suffer_score = act.get("suffer_score")
        start_date   = act.get("start_date", "")[:10]

        activities.append({
            "id":           act.get("id"),
            "date":         start_date,
            "start_time":   act.get("start_date_local", "")[:16].replace("T", " "),
            "type":         act_type,
            "name":         act.get("name", "Activité"),
            "description":  act.get("description") or "",
            "distance_km":  distance_km,
            "duration_min": _format_duration(elapsed_s),
            "moving_time":  _hms(moving_s),
            "elapsed_time": _hms(elapsed_s),
            "pace":         _format_pace(speed_ms, act_type),
            "avg_hr":       int(avg_hr) if avg_hr else None,
            "max_hr":       int(max_hr) if max_hr else None,
            "elevation_m":  elevation_m,
            "calories":     int(calories) if calories else None,
            "avg_cadence":  round(avg_cadence) if avg_cadence else None,
            "avg_watts":    round(avg_watts) if avg_watts else None,
            "suffer_score": int(suffer_score) if suffer_score else None,
            "kudos":        act.get("kudos_count", 0),
            "strava_url":   f"https://www.strava.com/activities/{act.get('id')}",
        })

        total_distance_m  += act.get("distance", 0)
        total_duration_s  += elapsed_s
        total_elevation_m += act.get("total_elevation_gain", 0)

    activities.sort(key=lambda x: x["date"], reverse=True)

    return {
        "athlete":     athlete_name,
        "period_days": days,
        "summary_ai":  "",
        "stats": {
            "total_activities":   len(activities),
            "total_distance_km":  round(total_distance_m / 1000, 1),
            "total_duration_min": _format_duration(total_duration_s),
            "total_elevation_m":  round(total_elevation_m),
        },
        "activities":    activities,
        "weekly_stats":  _build_weekly_stats(activities, days),
    }


if __name__ == "__main__":
    import json
    data = fetch_activities()
    print(json.dumps(data, indent=2, ensure_ascii=False))
