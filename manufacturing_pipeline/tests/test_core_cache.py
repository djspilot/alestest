import json
import os
import tempfile
import pytest

from manufacturing_pipeline.core.cache import (
    get_file_hash,
    load_cache,
    save_cache,
    get_cached_result,
    cache_result,
)


def test_get_file_hash_deterministic(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("hello world")
    h1 = get_file_hash(str(f))
    h2 = get_file_hash(str(f))
    assert h1 == h2
    assert isinstance(h1, str)
    assert len(h1) == 32  # MD5 hex digest


def test_get_file_hash_changes_with_content(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("version 1")
    h1 = get_file_hash(str(f))
    f.write_text("version 2")
    h2 = get_file_hash(str(f))
    assert h1 != h2


def test_load_cache_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr("manufacturing_pipeline.core.cache.CACHE_FILE", str(tmp_path / "nope.json"))
    assert load_cache() == {}


def test_load_cache_corrupt_json(tmp_path, monkeypatch):
    bad = tmp_path / "bad.json"
    bad.write_text("{broken")
    monkeypatch.setattr("manufacturing_pipeline.core.cache.CACHE_FILE", str(bad))
    assert load_cache() == {}


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    cache_path = str(tmp_path / "sub" / "cache.json")
    monkeypatch.setattr("manufacturing_pipeline.core.cache.CACHE_FILE", cache_path)
    data = {"key": {"hash": "abc", "result": 42}}
    save_cache(data)
    loaded = load_cache()
    assert loaded == data


def test_cache_result_and_retrieve(tmp_path):
    f = tmp_path / "part.step"
    f.write_bytes(b"STEP DATA")
    cache = {}
    cache = cache_result(str(f), {"holes": 5}, cache)
    result = get_cached_result(str(f), cache)
    assert result == {"holes": 5}


def test_cached_result_invalidated_on_change(tmp_path):
    f = tmp_path / "part.step"
    f.write_bytes(b"v1")
    cache = {}
    cache = cache_result(str(f), {"v": 1}, cache)
    f.write_bytes(b"v2")
    result = get_cached_result(str(f), cache)
    assert result is None
