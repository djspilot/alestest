"""API-configuratie geladen uit omgevingsvariabelen."""

import os

# API-sleutels (kommagescheiden in env)
API_KEYS: list[str] = [
    k.strip() for k in os.environ.get("API_KEYS", "").split(",") if k.strip()
]

# Bestandsupload-instellingen
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/tmp/manufacturing-uploads")
MAX_FILE_SIZE_MB = int(os.environ.get("MAX_FILE_SIZE_MB", "100"))

# Taakinstellingen
JOB_TTL_SECONDS = int(os.environ.get("JOB_TTL_SECONDS", "3600"))

# Databasepad voor persistente taakhistorie
DB_PATH = os.environ.get("DB_PATH", os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "db", "manufacturing_data.db"
))

# Toegestane STEP-bestandsextensies
ALLOWED_EXTENSIONS = {".step", ".stp"}
