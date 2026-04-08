"""
analyze.py
----------
Utilise Claude (claude-opus-4-6 avec adaptive thinking) pour générer :
  1. Un résumé narratif des activités Strava
  2. Un résumé de l'état de forme Garmin
  3. 4-5 idées de sorties sportives adaptées

Nécessite ANTHROPIC_API_KEY dans l'environnement.
"""

import json
import os
import anthropic


# ── Client ────────────────────────────────────────────────────────────────────
def _get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY manquante.")
    return anthropic.Anthropic(api_key=api_key)


# ── Prompt builder ────────────────────────────────────────────────────────────
def _build_prompt(strava: dict, garmin: dict) -> str:
    """Construit le prompt avec les données brutes."""

    strava_lines = []
    for act in strava.get("activities", []):
        hr_str = f" | FC moy {act['avg_hr']} bpm" if act.get("avg_hr") else ""
        strava_lines.append(
            f"  - {act['date']} · {act['type']} · {act['name']} : "
            f"{act['distance_km']} km en {act['duration_min']} min "
            f"({act['pace']}){hr_str} | D+ {act['elevation_m']} m"
        )

    stats = strava.get("stats", {})
    strava_block = f"""
=== STRAVA — {stats.get('total_activities', 0)} activité(s) sur {strava.get('period_days', 7)} jours ===
Distance totale : {stats.get('total_distance_km', 0)} km
Durée totale    : {stats.get('total_duration_min', 0)} min
Dénivelé total  : {stats.get('total_elevation_m', 0)} m

Détail des activités :
{chr(10).join(strava_lines) if strava_lines else "  (aucune activité)"}
""".strip()

    m = garmin.get("metrics", {})
    garmin_block = f"""
=== GARMIN CONNECT — Métriques de santé ===
FC de repos      : {m.get('resting_hr_bpm', 'N/A')} bpm
VFC (HRV)        : {m.get('hrv_ms', 'N/A')} ms
Poids            : {m.get('weight_kg', 'N/A')} kg
Score de stress  : {m.get('stress_score', 'N/A')} / 100
Sommeil          : {m.get('sleep_hours', 'N/A')} h
Body Battery     : {m.get('body_battery', 'N/A')} %

Tendances 7 jours :
  FC repos  : {garmin.get('trend', {}).get('resting_hr_7d', [])}
  VFC       : {garmin.get('trend', {}).get('hrv_7d', [])}
""".strip()

    prompt = f"""Tu es un coach sportif expert en analyse de performance et de récupération.
Voici les données de {strava.get('athlete', 'l\'athlète')} :

{strava_block}

{garmin_block}

Ta mission est de produire une analyse structurée en JSON avec exactement ce format :

{{
  "strava_summary": "Un résumé narratif chaleureux et motivant de la semaine d'entraînement (2-3 phrases). Mentionne les points forts, la progression et un encouragement.",
  "garmin_summary": "Un résumé de l'état de forme actuel (2-3 phrases). Interprète la VFC, la FC repos, le sommeil et le stress de façon concrète et actionnable.",
  "suggestions": [
    {{
      "icon": "emoji approprié",
      "type": "Run|Vélo|Trail|Natation|Récupération|Renforcement|autre",
      "title": "Titre court de la séance",
      "description": "Description motivante de 1-2 phrases avec des conseils concrets adaptés à l'état de forme actuel.",
      "difficulty": "Très facile|Facile|Modérée|Élevée",
      "duration": "Durée estimée (ex: 45 min, 1h30)"
    }}
  ]
}}

Contraintes pour les suggestions :
- Propose exactement 4 idées
- Adapte l'intensité à l'état de forme Garmin (si VFC basse ou stress élevé → favorise récupération)
- Varie les types de sport (pas 4 runs)
- Les descriptions doivent être personnalisées aux données, pas génériques
- Réponds uniquement avec le JSON, sans texte avant ou après"""

    return prompt


# ── Claude call ───────────────────────────────────────────────────────────────
def generate_analysis(strava: dict, garmin: dict) -> dict:
    """
    Appelle Claude et retourne un dict avec :
      strava_summary, garmin_summary, suggestions
    """
    client = _get_client()
    prompt = _build_prompt(strava, garmin)

    print("[Claude] Génération de l'analyse…")

    # Streaming avec adaptive thinking pour une meilleure qualité d'analyse
    with client.messages.stream(
        model="claude-opus-4-6",
        max_tokens=2048,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        response = stream.get_final_message()

    # Extrait le texte de la réponse
    full_text = ""
    for block in response.content:
        if block.type == "text":
            full_text = block.text
            break

    # Parse le JSON retourné par Claude
    # Nettoie les éventuels backticks (```json ... ```)
    clean = full_text.strip()
    if clean.startswith("```"):
        lines = clean.split("\n")
        clean = "\n".join(
            line for line in lines
            if not line.strip().startswith("```")
        ).strip()

    try:
        result = json.loads(clean)
    except json.JSONDecodeError as e:
        print(f"[Claude] Erreur JSON : {e}\nRéponse brute :\n{full_text[:500]}")
        # Fallback : retourne des valeurs par défaut
        result = {
            "strava_summary": "Analyse indisponible — erreur de parsing.",
            "garmin_summary": "Analyse indisponible — erreur de parsing.",
            "suggestions": [],
        }

    print(f"[Claude] ✓ Résumé Strava : {result.get('strava_summary', '')[:80]}…")
    return result


if __name__ == "__main__":
    # Test avec des données fictives
    test_strava = {
        "athlete": "Pierre",
        "period_days": 7,
        "stats": {"total_activities": 3, "total_distance_km": 35.0,
                  "total_duration_min": 180, "total_elevation_m": 200},
        "activities": [
            {"date": "2026-04-07", "type": "Run", "name": "Sortie longue",
             "distance_km": 18.2, "duration_min": 102, "pace": "5:36/km",
             "avg_hr": 142, "elevation_m": 145},
        ],
    }
    test_garmin = {
        "metrics": {"resting_hr_bpm": 48, "hrv_ms": 58, "weight_kg": 73.2,
                    "stress_score": 32, "sleep_hours": 7.4, "body_battery": 78},
        "trend": {"resting_hr_7d": [50, 49, 51, 48, 48, 47, 48],
                  "hrv_7d": [54, 56, 52, 58, 60, 57, 58]},
    }
    result = generate_analysis(test_strava, test_garmin)
    print(json.dumps(result, indent=2, ensure_ascii=False))
