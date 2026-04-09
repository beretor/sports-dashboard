"""
analyze.py
----------
Utilise Claude (claude-opus-4-6) pour générer :
  1. Un résumé narratif des activités Strava (30 jours)
  2. 4 idées de sorties sportives

Nécessite ANTHROPIC_API_KEY dans l'environnement.
"""

import json
import os
import anthropic


def _get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY manquante.")
    return anthropic.Anthropic(api_key=api_key)


def _build_prompt(strava: dict) -> str:
    stats = strava.get("stats", {})
    lines = []
    for act in strava.get("activities", [])[:20]:  # max 20 pour le prompt
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

    return f"""Tu es un coach sportif expert. Analyse les données de {strava.get('athlete', 'l\'athlète')} :

{strava_block}

Réponds UNIQUEMENT avec ce JSON (sans texte avant/après) :

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


def generate_analysis(strava: dict) -> dict:
    client = _get_client()
    prompt = _build_prompt(strava)

    print("[Claude] Génération de l'analyse…")

    with client.messages.stream(
        model="claude-opus-4-6",
        max_tokens=1024,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        response = stream.get_final_message()

    full_text = next((b.text for b in response.content if b.type == "text"), "")

    # Nettoie les backticks éventuels
    clean = full_text.strip()
    if clean.startswith("```"):
        clean = "\n".join(
            l for l in clean.split("\n") if not l.strip().startswith("```")
        ).strip()

    try:
        result = json.loads(clean)
    except json.JSONDecodeError as e:
        print(f"[Claude] Erreur JSON : {e}")
        result = {"strava_summary": "Analyse indisponible.", "suggestions": []}

    print(f"[Claude] ✓ {len(result.get('suggestions', []))} suggestions générées")
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
