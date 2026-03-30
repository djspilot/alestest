"""Single source of truth for project path constants."""

import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DATA_DIR = os.path.join(PROJECT_ROOT, "data")
CONFIG_DIR = os.path.join(DATA_DIR, "config")
DB_DIR = os.path.join(DATA_DIR, "db")
PARTS_DIR = os.path.join(DATA_DIR, "input")
OUTPUT_DIR = os.path.join(DATA_DIR, "output")

PIPELINE_DIR = os.path.join(PROJECT_ROOT, "manufacturing_pipeline")
SCRIPTS_DIR = os.path.join(PIPELINE_DIR, "scripts")

CACHE_FILE = os.path.join(DB_DIR, "pipeline_cache.json")
