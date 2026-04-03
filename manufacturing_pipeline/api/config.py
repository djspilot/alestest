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
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "db", "manufacturing_data.db"
))

# Toegestane STEP-bestandsextensies
ALLOWED_EXTENSIONS = {".step", ".stp"}

# All valid stage keys that can be disabled
VALID_STAGE_KEYS = {"classify_geometry", "profile_router", "detect_holes_pre_unfold", "unfold", "detect_holes", "aag"}

# Viewer/API defaults: skip noisy pre-routing and pre-unfold hole snapshot unless explicitly re-enabled in code.
DEFAULT_DISABLE_STAGES = {"profile_router", "detect_holes_pre_unfold"}

# Comma-separated list of additional stages to disable by default
DISABLE_STAGES: set[str] = DEFAULT_DISABLE_STAGES | {
    s.strip() for s in os.environ.get("DISABLE_STAGES", "").split(",") if s.strip()
}
