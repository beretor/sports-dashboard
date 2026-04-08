"""
garmin_export_tokens.py
-----------------------
Génère les tokens Garmin en local et les exporte en base64
pour les stocker dans GitHub Secrets (GARMIN_TOKENS).

Usage (une seule fois) :
  python scripts/garmin_export_tokens.py
"""

import base64
import os
import sys
import zipfile
import tempfile
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

from garminconnect import Garmin

email    = os.environ.get("GARMIN_EMAIL")
password = os.environ.get("GARMIN_PASSWORD")

if not email or not password:
    print("❌  GARMIN_EMAIL et GARMIN_PASSWORD requis dans .env")
    sys.exit(1)

# Dossier temporaire pour les tokens
token_dir = Path(tempfile.mkdtemp()) / "garth_tokens"
token_dir.mkdir()

print(f"[Garmin] Connexion avec {email}…")
client = Garmin(email=email, password=password)
client.login()

# Sauvegarde les tokens garth dans le dossier temporaire
client.garth.dump(str(token_dir))
print(f"[Garmin] ✓ Tokens sauvegardés dans {token_dir}")

# Zip + base64 encode
zip_path = token_dir.parent / "garmin_tokens.zip"
with zipfile.ZipFile(zip_path, "w") as zf:
    for f in token_dir.iterdir():
        zf.write(f, f.name)

encoded = base64.b64encode(zip_path.read_bytes()).decode()

print("\n" + "=" * 60)
print("  ✅  GARMIN_TOKENS (à copier dans GitHub Secrets)")
print("=" * 60)
print()
print(encoded)
print()
print("=" * 60)
print("  👉 GitHub → Settings → Secrets → New repository secret")
print("     Nom    : GARMIN_TOKENS")
print("     Valeur : (la longue chaîne ci-dessus)")
print("=" * 60)
