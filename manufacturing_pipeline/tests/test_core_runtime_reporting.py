"""
runtime_reporting.run_debug requires OCP and a real STEP file.
We test that the module imports cleanly and the function signature exists.
Full integration testing requires STEP fixtures.
"""
import pytest

from manufacturing_pipeline.core.runtime_reporting import run_debug


def test_run_debug_callable():
    assert callable(run_debug)


def test_run_debug_rejects_missing_file():
    """run_debug should fail on a non-existent file (load_step_file raises)."""
    with pytest.raises(Exception):
        run_debug("/nonexistent/file.step")
