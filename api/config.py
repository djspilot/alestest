"""API configuration loaded from environment variables."""

import os

# API keys (comma-separated in env)
API_KEYS: list[str] = [
    k.strip() for k in os.environ.get("API_KEYS", "").split(",") if k.strip()
]

# File upload settings
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/tmp/manufacturing-uploads")
MAX_FILE_SIZE_MB = int(os.environ.get("MAX_FILE_SIZE_MB", "100"))

# Job settings
JOB_TTL_SECONDS = int(os.environ.get("JOB_TTL_SECONDS", "3600"))

# Allowed STEP file extensions
ALLOWED_EXTENSIONS = {".step", ".stp"}
