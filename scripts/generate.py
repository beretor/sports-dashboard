"""
generate.py
-----------
Point d'entrée principal du pipeline :
  1. Fetch Strava  → données activités
  2. Fetch Garmin  → métriques santé
  3. Claude API    → résumés + suggestions
  4. Écrit docs/data.json

Usage :
  python scripts/generate.py

Variables d'environnement requises (dans .env ou GitHub Secrets) :
  STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REFRESH_TOKEN
  GARMIN_EMAIL (ou tokens ~/.garminconnect)
  GARMIN_PASSWORD (ou tokens ~/.garminconnect)
  ANTHROPIC_API_KEY
"""

import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

# Chargement optionnel de .env (pour développement local)
try:
    from dotenv import load_dotenv
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
        print(f"[Config] .env chargé depuis {env_file}")
except ImportError:
    pass  # python-dotenv non installé → on utilise les vraies variables d'env

# Ajoute le dossier scripts/ au path pour les imports relatifs
sys.path.insert(0, str(Path(__file__).parent))

from fetch_strava import fetch_activities
from fetch_garmin import fetch_health
from analyze     import generate_analysis

# Chemin de sortie
OUTPUT_FILE = Path(__file__).parent.parent / "docs" / "data.json"


# ── Pipeline ──────────────────────────────────────────────────────────────────
def run():
    print("=" * 60)
    print("  Sports Dashboard — Génération des données")
    print("=" * 60)

    errors = []

    # ── 1. Strava ──────────────────────────────────────────────────
    print("\n[1/3] Récupération Strava…")
    strava_data = None
    try:
        strava_data = fetch_activities(days=7)
        print(f"  ✓ {strava_data['stats']['total_activities']} activité(s) "
              f"({strava_data['stats']['total_distance_km']} km)")
    except Exception as e:
        print(f"  ✗ Erreur Strava : {e}")
        traceback.print_exc()
        errors.append(f"Strava : {e}")
        # Fallback : données vides
        strava_data = {
            "athlete": "Athlète",
            "period_days": 7,
            "summary_ai": "Données Strava indisponibles.",
            "stats": {"total_activities": 0, "total_distance_km": 0,
                      "total_duration_min": 0, "total_elevation_m": 0},
            "activities": [],
        }

    # ── 2. Garmin ──────────────────────────────────────────────────
    print("\n[2/3] Récupération Garmin Connect…")
    garmin_data = None
    try:
        garmin_data = fetch_health(days=7)
        m = garmin_data["metrics"]
        print(f"  ✓ FC repos={m.get('resting_hr_bpm')} bpm | "
              f"VFC={m.get('hrv_ms')} ms | "
              f"Poids={m.get('weight_kg')} kg")
    except Exception as e:
        print(f"  ✗ Erreur Garmin : {e}")
        traceback.print_exc()
        errors.append(f"Garmin : {e}")
        garmin_data = {
            "summary_ai": "Données Garmin indisponibles.",
            "metrics": {
                "resting_hr_bpm": None,
                "hrv_ms": None,
                "weight_kg": None,
                "stress_score": None,
                "sleep_hours": None,
                "body_battery": None,
            },
            "trend": {
                "resting_hr_7d": [],
                "hrv_7d": [],
            },
        }

    # ── 3. Claude ──────────────────────────────────────────────────
    print("\n[3/3] Analyse Claude (claude-opus-4-6)…")
    suggestions = []
    try:
        analysis = generate_analysis(strava_data, garmin_data)

        # Injecte les résumés IA dans les données
        strava_data["summary_ai"] = analysis.get("strava_summary", "")
        garmin_data["summary_ai"] = analysis.get("garmin_summary", "")
        suggestions = analysis.get("suggestions", [])

        print(f"  ✓ {len(suggestions)} suggestion(s) générée(s)")
    except Exception as e:
        print(f"  ✗ Erreur Claude : {e}")
        traceback.print_exc()
        errors.append(f"Claude : {e}")
        strava_data["summary_ai"] = "Résumé IA indisponible."
        garmin_data["summary_ai"] = "Résumé IA indisponible."

    # ── 4. Écriture du JSON ────────────────────────────────────────
    output = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "strava":       strava_data,
        "garmin":       garmin_data,
        "suggestions":  suggestions,
    }
    if errors:
        output["errors"] = errors

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n✅ data.json généré : {OUTPUT_FILE}")
    if errors:
        print(f"⚠️  Erreurs partielles : {errors}")
    print("=" * 60)


if __name__ == "__main__":
    run()
