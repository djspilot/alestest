import os
import pytest

from manufacturing_pipeline.core.file_utils import (
    find_step_files,
    get_output_dir,
)


def test_find_step_files_empty_dir(tmp_path):
    assert find_step_files(str(tmp_path)) == []


def test_find_step_files_finds_step(tmp_path):
    (tmp_path / "part.step").write_text("STEP")
    (tmp_path / "other.txt").write_text("nope")
    files = find_step_files(str(tmp_path))
    assert len(files) >= 1
    assert any(f.endswith("part.step") for f in files)


def test_find_step_files_finds_stp(tmp_path):
    (tmp_path / "part.stp").write_text("STEP")
    files = find_step_files(str(tmp_path))
    assert len(files) >= 1


def test_find_step_files_case_insensitive(tmp_path):
    (tmp_path / "part.STEP").write_text("STEP")
    files = find_step_files(str(tmp_path))
    assert len(files) >= 1


def test_find_step_files_recursive(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "nested.step").write_text("STEP")
    files = find_step_files(str(tmp_path))
    assert len(files) >= 1
    assert any("nested.step" in f for f in files)


def test_find_step_files_nonexistent_dir():
    assert find_step_files("/nonexistent/path/xyz") == []


def test_get_output_dir_creates_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("manufacturing_pipeline.core.file_utils.OUTPUT_DIR", str(tmp_path))
    out_dir, name = get_output_dir("/fake/path/mypart.step")
    assert name == "mypart"
    assert out_dir.endswith("mypart")
    assert os.path.isdir(out_dir)


def test_get_output_dir_strips_extension(tmp_path, monkeypatch):
    monkeypatch.setattr("manufacturing_pipeline.core.file_utils.OUTPUT_DIR", str(tmp_path))
    _, name = get_output_dir("/path/to/complex.name.step")
    assert name == "complex.name"
