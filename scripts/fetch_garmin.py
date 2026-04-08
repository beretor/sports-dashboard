"""
fetch_garmin.py
---------------
Récupère les métriques de santé Garmin Connect des 7 derniers jours :
  - FC de repos
  - VFC (HRV)
  - Poids
  - Score de stress
  - Heures de sommeil
  - Body Battery

Authentification : email + mot de passe via les variables d'env
  GARMIN_EMAIL
  GARMIN_PASSWORD

Ou via les tokens stockés localement (~/.garminconnect ou ~/.garth).
"""

import os
import json
import statistics
from datetime import date, timedelta

from garminconnect import Garmin


# ── Auth ──────────────────────────────────────────────────────────────────────
def _init_client() -> Garmin:
    """Connexion Garmin via tokens stockés (garth)."""
    token_paths = [
        os.path.expanduser("~/.garth"),           # restauré par GitHub Actions
        os.path.expanduser("~/.garminconnect"),    # ancien format
        os.path.expanduser("~/.claude-coach/garmin_tokens.json"),  # local
    ]

    for token_path in token_paths:
        if os.path.exists(token_path):
            try:
                client = Garmin()
                client.login(token_path)
                print(f"[Garmin] ✓ Connecté via tokens : {token_path}")
                return client
            except Exception as e:
                print(f"[Garmin] Tokens invalides ({token_path}) : {e}")

    raise EnvironmentError(
        "Garmin : aucun token valide trouvé dans ~/.garth, ~/.garminconnect "
        "ou ~/.claude-coach/garmin_tokens.json.\n"
        "Lance 'python scripts/garmin_export_tokens.py' en local."
    )


# ── Helpers ───────────────────────────────────────────────────────────────────
def _safe_get(data: dict, *keys, default=None):
    """Navigue dans un dict imbriqué sans KeyError."""
    for key in keys:
        if not isinstance(data, dict):
            return default
        data = data.get(key, default)
        if data is None:
            return default
    return data


def _date_range(days: int = 7) -> list[str]:
    """Retourne les N derniers jours au format YYYY-MM-DD."""
    today = date.today()
    return [(today - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]


# ── Fetchers par métrique ─────────────────────────────────────────────────────
def _fetch_resting_hr(client: Garmin, days: list[str]) -> tuple[int | None, list[int]]:
    """FC de repos du jour + tendance 7j."""
    trend = []
    for d in days:
        try:
            data = client.get_rhr_day(d)
            val  = _safe_get(data, "allMetrics", "metricsMap", "WELLNESS_RESTING_HEART_RATE")
            if val and isinstance(val, list):
                trend.append(int(val[0].get("value", 0)) or None)
            else:
                trend.append(None)
        except Exception:
            trend.append(None)

    # Remplace les None par interpolation simple
    valid = [v for v in trend if v is not None]
    cleaned = [v if v is not None else (valid[-1] if valid else 0) for v in trend]
    latest  = next((v for v in reversed(trend) if v is not None), None)
    return latest, cleaned


def _fetch_hrv(client: Garmin, days: list[str]) -> tuple[int | None, list[int]]:
    """VFC (HRV) du dernier jour disponible + tendance 7j."""
    trend = []
    for d in days:
        try:
            data = client.get_hrv_data(d)
            val  = _safe_get(data, "hrvSummary", "lastNight")
            trend.append(int(val) if val else None)
        except Exception:
            trend.append(None)

    valid   = [v for v in trend if v is not None]
    cleaned = [v if v is not None else (valid[-1] if valid else 0) for v in trend]
    latest  = next((v for v in reversed(trend) if v is not None), None)
    return latest, cleaned


def _fetch_weight(client: Garmin, days: list[str]) -> float | None:
    """Dernier poids enregistré."""
    for d in reversed(days):
        try:
            data = client.get_body_composition(d)
            entries = _safe_get(data, "dateWeightList", default=[])
            if entries:
                kg = entries[-1].get("weight", None)
                if kg:
                    return round(kg / 1000, 1)  # Garmin stocke en grammes
        except Exception:
            continue
    return None


def _fetch_stress(client: Garmin, today: str) -> int | None:
    """Score de stress moyen du jour (0-100)."""
    try:
        data = client.get_stress_data(today)
        val  = _safe_get(data, "avgStressLevel")
        return int(val) if val and val > 0 else None
    except Exception:
        return None


def _fetch_sleep(client: Garmin, today: str) -> float | None:
    """Heures de sommeil de la nuit précédente."""
    try:
        data = client.get_sleep_data(today)
        secs = _safe_get(data, "dailySleepDTO", "sleepTimeSeconds")
        if secs:
            return round(secs / 3600, 1)
    except Exception:
        pass
    return None


def _fetch_body_battery(client: Garmin, today: str) -> int | None:
    """Body Battery maximum du jour (énergie de départ)."""
    try:
        data = client.get_body_battery(today, today)
        if data and isinstance(data, list):
            charged = data[0].get("charged", None)
            if charged:
                return int(charged)
    except Exception:
        pass
    return None


# ── Main fetch ────────────────────────────────────────────────────────────────
def fetch_health(days: int = 7) -> dict:
    """
    Retourne un dict prêt à être injecté dans data.json section 'garmin'.
    """
    client  = _init_client()
    dates   = _date_range(days)
    today   = dates[-1]

    print(f"[Garmin] Récupération des données du {dates[0]} au {today}…")

    resting_hr, hr_trend  = _fetch_resting_hr(client, dates)
    hrv, hrv_trend        = _fetch_hrv(client, dates)
    weight                = _fetch_weight(client, dates)
    stress                = _fetch_stress(client, today)
    sleep_hours           = _fetch_sleep(client, today)
    body_battery          = _fetch_body_battery(client, today)

    print(f"[Garmin] FC repos={resting_hr}, VFC={hrv}, poids={weight}kg, "
          f"stress={stress}, sommeil={sleep_hours}h, battery={body_battery}")

    return {
        "summary_ai": "",   # rempli par analyze.py
        "metrics": {
            "resting_hr_bpm":  resting_hr,
            "hrv_ms":          hrv,
            "weight_kg":       weight,
            "stress_score":    stress,
            "sleep_hours":     sleep_hours,
            "body_battery":    body_battery,
        },
        "trend": {
            "resting_hr_7d": hr_trend,
            "hrv_7d":        hrv_trend,
        },
    }


if __name__ == "__main__":
    data = fetch_health()
    print(json.dumps(data, indent=2, ensure_ascii=False))
