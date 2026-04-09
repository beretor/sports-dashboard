"""
generate.py — Point d'entrée principal
  1. Fetch Strava (30j)
  2. Claude API → résumé + suggestions
  3. Écrit docs/data.json
"""

import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
        print(f"[Config] .env chargé")
except ImportError:
    pass

sys.path.insert(0, str(Path(__file__).parent))

from fetch_strava import fetch_activities
from analyze     import generate_analysis

OUTPUT_FILE = Path(__file__).parent.parent / "docs" / "data.json"


def run():
    print("=" * 60)
    print("  Sports Dashboard — Génération des données")
    print("=" * 60)

    errors = []

    # ── 1. Strava ──────────────────────────────────────────────────
    print("\n[1/2] Récupération Strava (30 jours)…")
    strava_data = None
    try:
        strava_data = fetch_activities(days=30)
        print(f"  ✓ {strava_data['stats']['total_activities']} activité(s) "
              f"— {strava_data['stats']['total_distance_km']} km")
    except Exception as e:
        print(f"  ✗ Erreur Strava : {e}")
        traceback.print_exc()
        errors.append(f"Strava : {e}")
        strava_data = {
            "athlete": "Athlète", "period_days": 30, "summary_ai": "",
            "stats": {"total_activities": 0, "total_distance_km": 0,
                      "total_duration_min": 0, "total_elevation_m": 0},
            "activities": [], "weekly_stats": [],
        }

    # ── 2. Claude ──────────────────────────────────────────────────
    print("\n[2/2] Analyse Claude…")
    suggestions = []
    try:
        analysis = generate_analysis(strava_data)
        strava_data["summary_ai"] = analysis.get("strava_summary", "")
        suggestions = analysis.get("suggestions", [])
    except Exception as e:
        print(f"  ✗ Erreur Claude : {e}")
        traceback.print_exc()
        errors.append(f"Claude : {e}")
        strava_data["summary_ai"] = ""

    # ── 3. Écriture ────────────────────────────────────────────────
    output = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "strava":       strava_data,
        "suggestions":  suggestions,
    }
    if errors:
        output["errors"] = errors

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n✅ data.json généré : {OUTPUT_FILE}")
    if errors:
        print(f"⚠️  Erreurs : {errors}")
    print("=" * 60)


if __name__ == "__main__":
    run()
