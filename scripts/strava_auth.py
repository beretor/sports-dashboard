"""
strava_auth.py
--------------
Script one-shot pour obtenir ton STRAVA_REFRESH_TOKEN initial.
À lancer UNE SEULE FOIS en local, puis copier le token dans GitHub Secrets.

Usage :
  1. Met STRAVA_CLIENT_ID et STRAVA_CLIENT_SECRET dans .env (ou passe-les en env)
  2. Lance :  python scripts/strava_auth.py
  3. Ouvre l'URL affichée dans ton navigateur
  4. Autorise l'app Strava
  5. Copie le code de l'URL de redirection quand on te le demande
  6. Le refresh_token s'affiche → copie-le dans GitHub Secrets
"""

import os
import sys
import webbrowser
import requests
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

CLIENT_ID     = os.environ.get("STRAVA_CLIENT_ID")
CLIENT_SECRET = os.environ.get("STRAVA_CLIENT_SECRET")

if not CLIENT_ID or not CLIENT_SECRET:
    print("❌  STRAVA_CLIENT_ID et STRAVA_CLIENT_SECRET doivent être définis.")
    print("    Mets-les dans .env ou exporte-les dans ton terminal.")
    sys.exit(1)

# ── Étape 1 : URL d'autorisation ──────────────────────────────────────────────
AUTH_URL = (
    f"https://www.strava.com/oauth/authorize"
    f"?client_id={CLIENT_ID}"
    f"&redirect_uri=http://localhost"
    f"&response_type=code"
    f"&scope=read,activity:read_all"
)

print("\n" + "=" * 60)
print("  Strava OAuth — Obtention du refresh_token")
print("=" * 60)
print("\n1. Ouvre cette URL dans ton navigateur :\n")
print(f"   {AUTH_URL}\n")

try:
    webbrowser.open(AUTH_URL)
    print("   (ouverture automatique tentée…)")
except Exception:
    pass

# ── Étape 2 : Code retourné par Strava ────────────────────────────────────────
print("\n2. Après avoir autorisé l'app, Strava te redirige vers :")
print("   http://localhost/?state=&code=XXXXXXX&scope=...")
print("\n3. Copie uniquement la valeur du paramètre 'code=' :")
print()
code = input("   Code : ").strip()

if not code:
    print("❌  Aucun code fourni.")
    sys.exit(1)

# ── Étape 3 : Échange du code contre les tokens ───────────────────────────────
print("\n4. Échange du code contre les tokens…")
resp = requests.post(
    "https://www.strava.com/oauth/token",
    data={
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code":          code,
        "grant_type":    "authorization_code",
    },
    timeout=15,
)

if not resp.ok:
    print(f"❌  Erreur {resp.status_code} : {resp.text}")
    sys.exit(1)

data = resp.json()

# ── Résultat ──────────────────────────────────────────────────────────────────
refresh_token = data.get("refresh_token", "")
access_token  = data.get("access_token", "")
athlete       = data.get("athlete", {})
name          = f"{athlete.get('firstname', '')} {athlete.get('lastname', '')}".strip()

print("\n" + "=" * 60)
print(f"  ✅  Authentifié en tant que : {name}")
print("=" * 60)
print(f"\n  STRAVA_REFRESH_TOKEN = {refresh_token}")
print()
print("  👉 Copie cette valeur dans GitHub Secrets :")
print("     Repo → Settings → Secrets → New repository secret")
print("     Nom : STRAVA_REFRESH_TOKEN")
print(f"     Valeur : {refresh_token}")
print()
print("  ⚠️  Ne committe pas ce token dans Git !")
print("=" * 60 + "\n")
