"""
fetch_strava_mcp.py
--------------------
Alternative à fetch_strava.py : utilise le serveur MCP @r-huijts/strava-mcp-server
pour récupérer les données Strava sans gérer l'OAuth manuellement.

Prérequis :
  - Node.js installé (npx disponible)
  - Compte Strava connecté via : claude → "Connect my Strava account"
    (les tokens sont stockés dans ~/.config/strava-mcp/config.json)

Usage :
  python scripts/fetch_strava_mcp.py
"""

import json
import subprocess
import threading
import time
from datetime import datetime, timedelta


# ── Client MCP minimal (stdio / JSON-RPC 2.0) ────────────────────────────────

class StravaMCPClient:
    def __init__(self):
        self._proc = subprocess.Popen(
            ["npx", "-y", "@r-huijts/strava-mcp-server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._id = 0
        self._lock = threading.Lock()
        self._initialize()

    def _send(self, method: str, params: dict = None) -> dict:
        with self._lock:
            self._id += 1
            msg = {"jsonrpc": "2.0", "id": self._id, "method": method}
            if params:
                msg["params"] = params
            self._proc.stdin.write(json.dumps(msg) + "\n")
            self._proc.stdin.flush()
            raw = self._proc.stdout.readline()
            return json.loads(raw)

    def _initialize(self):
        self._send("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "sports-dashboard", "version": "1.0"},
        })
        self._send("notifications/initialized")

    def call_tool(self, name: str, arguments: dict = None) -> dict:
        resp = self._send("tools/call", {
            "name": name,
            "arguments": arguments or {},
        })
        if "error" in resp:
            raise RuntimeError(f"MCP error [{name}]: {resp['error']}")
        content = resp.get("result", {}).get("content", [])
        for block in content:
            if block.get("type") == "text":
                try:
                    return json.loads(block["text"])
                except json.JSONDecodeError:
                    return {"raw": block["text"]}
        return {}

    def close(self):
        self._proc.stdin.close()
        self._proc.terminate()


# ── Formatters (identiques à fetch_strava.py) ────────────────────────────────

def _format_pace(speed_ms: float, activity_type: str) -> str:
    if speed_ms <= 0:
        return "—"
    if activity_type in ("Run", "Hike", "Walk", "TrailRun"):
        pace_sec = 1000 / speed_ms
        return f"{int(pace_sec // 60)}:{int(pace_sec % 60):02d}/km"
    return f"{speed_ms * 3.6:.1f} km/h"


def _format_duration(seconds: int) -> int:
    return round(seconds / 60)


def _hms(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _build_weekly_stats(activities: list) -> list:
    from collections import defaultdict
    weeks = defaultdict(lambda: {"distance_km": 0, "duration_min": 0,
                                  "count": 0, "elevation_m": 0})
    for act in activities:
        d = datetime.fromisoformat(act["date"])
        monday = (d - timedelta(days=d.weekday())).strftime("%Y-%m-%d")
        weeks[monday]["distance_km"]  += act["distance_km"]
        weeks[monday]["duration_min"] += act["duration_min"]
        weeks[monday]["elevation_m"]  += act["elevation_m"]
        weeks[monday]["count"]        += 1

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


# ── Fetch principal ───────────────────────────────────────────────────────────

def fetch_activities(days: int = 30) -> dict:
    client = StravaMCPClient()
    try:
        # Profil athlète
        profile = client.call_tool("get-athlete-profile")
        athlete_name = profile.get("firstname", "Athlète")

        # Activités récentes
        after_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        raw = client.call_tool("get-all-activities", {
            "after": after_date,
            "per_page": 100,
        })
        raw_activities = raw if isinstance(raw, list) else raw.get("activities", [])

        activities = []
        total_distance_m  = 0
        total_duration_s  = 0
        total_elevation_m = 0

        for act in raw_activities:
            act_type    = act.get("sport_type") or act.get("type", "Workout")
            distance_km = round(act.get("distance", 0) / 1000, 2)
            elapsed_s   = act.get("elapsed_time", 0)
            moving_s    = act.get("moving_time", elapsed_s)
            speed_ms    = act.get("average_speed", 0)
            avg_hr      = act.get("average_heartrate")
            max_hr      = act.get("max_heartrate")
            elevation_m = round(act.get("total_elevation_gain", 0))
            calories    = act.get("kilojoules") or act.get("calories")
            avg_cadence = act.get("average_cadence")
            avg_watts   = act.get("average_watts")
            suffer_score = act.get("suffer_score")
            start_date  = act.get("start_date", "")[:10]

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
            "activities":   activities,
            "weekly_stats": _build_weekly_stats(activities),
        }
    finally:
        client.close()


if __name__ == "__main__":
    data = fetch_activities()
    print(json.dumps(data, indent=2, ensure_ascii=False))
