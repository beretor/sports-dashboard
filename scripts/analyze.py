"""
analyze.py
----------
Utilise Gemini (gemini-2.0-flash) pour générer :
  1. Un résumé narratif des activités Strava (30 jours)
  2. 4 idées de sorties sportives

Nécessite GEMINI_API_KEY dans l'environnement.
Clé gratuite sur https://aistudio.google.com/apikey
"""

import json
import os
from google import genai


def _get_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY manquante.")
    return genai.Client(api_key=api_key)


def _build_prompt(strava: dict) -> str:
    stats = strava.get("stats", {})
    lines = []
    for act in strava.get("activities", [])[:20]:
        hr_str  = f" | FC {act['avg_hr']} bpm" if act.get("avg_hr") else ""
        cal_str = f" | {act['calories']} kcal" if act.get("calories") else ""
        lines.append(
            f"  - {act['date']} · {act['type']} · {act['name']} : "
            f"{act['distance_km']} km en {act['duration_min']} min "
            f"({act['pace']}){hr_str} | D+ {act['elevation_m']} m{cal_str}"
        )

    strava_block = f"""
=== STRAVA — {stats.get('total_activities', 0)} activité(s) sur {strava.get('period_days', 30)} jours ===
Distance totale : {stats.get('total_distance_km', 0)} km
Durée totale    : {stats.get('total_duration_min', 0)} min
Dénivelé total  : {stats.get('total_elevation_m', 0)} m

Activités récentes :
{chr(10).join(lines) if lines else "  (aucune activité)"}
""".strip()

    return f"""Tu es un coach sportif expert. Analyse les données de {strava.get('athlete', "l'athlète")} :

{strava_block}

Réponds UNIQUEMENT avec ce JSON (sans texte avant/après, sans balises markdown) :

{{
  "strava_summary": "Résumé narratif motivant de la période (2-3 phrases). Points forts, tendances, encouragement.",
  "suggestions": [
    {{
      "icon": "emoji",
      "type": "Run|Vélo|Trail|Natation|Récupération|Renforcement",
      "title": "Titre court",
      "description": "Description concrète et motivante (1-2 phrases) adaptée aux données.",
      "difficulty": "Très facile|Facile|Modérée|Élevée",
      "duration": "ex: 45 min"
    }}
  ]
}}

Contraintes : exactement 4 suggestions, variées (pas 4 runs), basées sur les vraies données."""


MODELS = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-2.0-flash-lite"]


def generate_analysis(strava: dict) -> dict:
    client = _get_client()
    prompt = _build_prompt(strava)

    print("[Gemini] Génération de l'analyse…")

    last_error = None
    for model in MODELS:
        try:
            print(f"[Gemini] Essai avec {model}…")
            response = client.models.generate_content(
                model=model,
                contents=prompt,
            )
            full_text = response.text.strip()
            break
        except Exception as e:
            print(f"[Gemini] ✗ {model} : {str(e)[:120]}")
            last_error = e
            continue
    else:
        raise last_error

    # Nettoie les backticks éventuels (```json ... ```)
    if full_text.startswith("```"):
        full_text = "\n".join(
            l for l in full_text.split("\n") if not l.strip().startswith("```")
        ).strip()

    try:
        result = json.loads(full_text)
    except json.JSONDecodeError as e:
        print(f"[Gemini] Erreur JSON : {e}\nRéponse : {full_text[:300]}")
        result = {"strava_summary": "Analyse indisponible.", "suggestions": []}

    print(f"[Gemini] ✓ {len(result.get('suggestions', []))} suggestions générées")
    return result


if __name__ == "__main__":
    test = {
        "athlete": "Pierre", "period_days": 30,
        "stats": {"total_activities": 12, "total_distance_km": 180,
                  "total_duration_min": 900, "total_elevation_m": 1200},
        "activities": [
            {"date": "2026-04-07", "type": "Run", "name": "Sortie longue",
             "distance_km": 18.2, "duration_min": 102, "pace": "5:36/km",
             "avg_hr": 142, "elevation_m": 145, "calories": 950},
        ],
    }
    print(json.dumps(generate_analysis(test), indent=2, ensure_ascii=False))
