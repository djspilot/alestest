import os
import pytest

from manufacturing_pipeline.core.paths import (
    PROJECT_ROOT,
    DATA_DIR,
    CONFIG_DIR,
    DB_DIR,
    PARTS_DIR,
    OUTPUT_DIR,
    PIPELINE_DIR,
    SCRIPTS_DIR,
    CACHE_FILE,
)


def test_project_root_exists():
    assert os.path.isdir(PROJECT_ROOT)
    assert os.path.exists(os.path.join(PROJECT_ROOT, "manufacturing_pipeline"))


def test_data_dir_under_root():
    assert DATA_DIR == os.path.join(PROJECT_ROOT, "data")


def test_parts_dir():
    assert PARTS_DIR == os.path.join(DATA_DIR, "input")


def test_output_dir():
    assert OUTPUT_DIR == os.path.join(DATA_DIR, "output")


def test_pipeline_dir():
    assert PIPELINE_DIR == os.path.join(PROJECT_ROOT, "manufacturing_pipeline")
    assert os.path.isdir(PIPELINE_DIR)


def test_cache_file_path():
    assert CACHE_FILE.endswith("pipeline_cache.json")
    assert DB_DIR in CACHE_FILE
