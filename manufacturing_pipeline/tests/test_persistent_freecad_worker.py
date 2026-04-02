from queue import Queue
from types import SimpleNamespace

from manufacturing_pipeline.core import runtime_unfold


def test_worker_attempt_uses_singleton_client(monkeypatch, tmp_path) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    step_file = tmp_path / "part.step"
    step_file.write_text("ISO-10303-21;")

    created = []

    class DummyClient:
        def __init__(self, sys_config) -> None:  # type: ignore[no-untyped-def]
            created.append(sys_config.freecad_python)

        def request(self, *, step_file, output_dir, part_name, timeout_seconds, variant):  # type: ignore[no-untyped-def]
            return {
                "success": True,
                "flat_length": 10.0,
                "flat_width": 5.0,
                "variant": variant,
            }

        def close(self) -> None:
            return None

    config = SimpleNamespace(
        freecad_python="/managed/python",
        freecad_path="/managed",
        freecad_cmd="/managed/FreeCADCmd",
        freecad_lib="/managed/lib",
        freecad_mod="/managed/Mod",
        _managed_runtime_value=lambda key: "/managed" if key == "runtime_root" else "",
    )

    monkeypatch.setattr(runtime_unfold, "_PersistentFreeCADWorkerClient", DummyClient)
    runtime_unfold._PERSISTENT_FREECAD_WORKERS.clear()

    first = runtime_unfold._run_direct_python_worker_attempt(str(step_file), str(output_dir), "part", config)
    second = runtime_unfold._run_direct_python_worker_attempt(str(step_file), str(output_dir), "part", config)

    assert first["success"] is True
    assert second["success"] is True
    assert first["runtime_source"] == "direct-freecad-python"
    assert len(created) == 1


def test_worker_attempt_reports_transport_failure(monkeypatch, tmp_path) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    step_file = tmp_path / "part.step"
    step_file.write_text("ISO-10303-21;")

    class BrokenClient:
        def __init__(self, sys_config) -> None:  # type: ignore[no-untyped-def]
            return None

        def request(self, **kwargs):  # type: ignore[no-untyped-def]
            raise RuntimeError("worker pipe closed")

        def close(self) -> None:
            return None

    config = SimpleNamespace(
        freecad_python="/managed/python",
        freecad_path="/managed",
        freecad_cmd="/managed/FreeCADCmd",
        freecad_lib="/managed/lib",
        freecad_mod="/managed/Mod",
        _managed_runtime_value=lambda key: "/managed" if key == "runtime_root" else "",
    )

    monkeypatch.setattr(runtime_unfold, "_PersistentFreeCADWorkerClient", BrokenClient)
    runtime_unfold._PERSISTENT_FREECAD_WORKERS.clear()

    result = runtime_unfold._run_direct_python_worker_attempt(str(step_file), str(output_dir), "part", config)

    assert result["success"] is False
    assert result["worker_transport_error"] is True
    assert "worker pipe closed" in result["error"]


def test_run_unfold_to_step_falls_back_to_one_shot_when_worker_transport_fails(monkeypatch, tmp_path) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    step_file = tmp_path / "part.step"
    step_file.write_text("ISO-10303-21;")

    calls = {"worker": 0, "oneshot": 0}

    monkeypatch.setenv("FREECAD_UNFOLD_MODE", "direct-python")
    monkeypatch.setattr(
        runtime_unfold,
        "_run_direct_unfold_attempt",
        lambda *args, **kwargs: {"success": False, "error": "host skipped"},
    )

    def fake_worker(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls["worker"] += 1
        return {"success": False, "error": "worker down", "worker_transport_error": True}

    def fake_oneshot(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls["oneshot"] += 1
        return {"success": True, "runtime_source": "direct-freecad-python"}

    monkeypatch.setattr(runtime_unfold.SystemConfig, "from_env", staticmethod(lambda: object()))
    monkeypatch.setattr(runtime_unfold, "_run_direct_python_worker_attempt", fake_worker)
    monkeypatch.setattr(runtime_unfold, "_run_unfold_subprocess_attempt", fake_oneshot)

    result = runtime_unfold.run_unfold_to_step(str(step_file), str(output_dir), "part", object())

    assert result["success"] is True
    assert calls["worker"] == 1
    assert calls["oneshot"] == 1
