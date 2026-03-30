from manufacturing_pipeline.core import freecad_runtime
from manufacturing_pipeline.core.config import SystemConfig


def test_configured_runtime_uses_managed_metadata(tmp_path):
    runtime_root = tmp_path / "freecad"
    (runtime_root / "bin").mkdir(parents=True)
    (runtime_root / "Mod").mkdir()
    (runtime_root / "lib").mkdir()
    (runtime_root / "bin" / "FreeCADCmd").write_text("")
    (runtime_root / "bin" / "python").write_text("")

    metadata_path = freecad_runtime.managed_runtime_metadata_path(str(tmp_path))
    freecad_runtime.save_runtime_metadata(
        {
            "runtime_root": str(runtime_root),
            "platform": "darwin",
        },
        metadata_path=metadata_path,
    )

    runtime = freecad_runtime.configured_runtime(str(tmp_path))

    assert runtime["runtime_root"] == str(runtime_root)
    assert runtime["freecad_cmd"] == str(runtime_root / "bin" / "FreeCADCmd")
    assert runtime["freecad_python"] == str(runtime_root / "bin" / "python")
    assert runtime["freecad_mod"] == str(runtime_root / "Mod")
    assert runtime["available"] is True


def test_system_config_prefers_managed_runtime_values(monkeypatch, tmp_path):
    runtime_root = tmp_path / "freecad"
    freecad_cmd = runtime_root / "bin" / "FreeCADCmd"
    freecad_python = runtime_root / "bin" / "python"
    freecad_lib = runtime_root / "lib"
    freecad_mod = runtime_root / "Mod"

    freecad_cmd.parent.mkdir(parents=True)
    freecad_lib.mkdir()
    freecad_mod.mkdir()
    freecad_cmd.write_text("")
    freecad_python.write_text("")

    monkeypatch.setattr(
        freecad_runtime,
        "configured_runtime",
        lambda project_root=None: {
            "freecad_cmd": str(freecad_cmd),
            "freecad_python": str(freecad_python),
            "freecad_lib": str(freecad_lib),
            "freecad_mod": str(freecad_mod),
        },
    )

    cfg = SystemConfig(freecad_path="/unused")

    assert cfg.freecad_cmd == str(freecad_cmd)
    assert cfg.freecad_python == str(freecad_python)
    assert cfg.freecad_lib == str(freecad_lib)
    assert cfg.freecad_mod == str(freecad_mod)


def test_ensure_managed_runtime_reuses_existing_runtime(monkeypatch, tmp_path):
    runtime_root = tmp_path / "freecad"
    freecad_cmd = runtime_root / "bin" / "FreeCADCmd"
    freecad_python = runtime_root / "bin" / "python"
    freecad_mod = runtime_root / "Mod"
    freecad_lib = runtime_root / "lib"

    freecad_cmd.parent.mkdir(parents=True)
    freecad_mod.mkdir()
    freecad_lib.mkdir()
    freecad_cmd.write_text("")
    freecad_python.write_text("")

    monkeypatch.setattr(freecad_runtime, "_verify_runtime", lambda info: {"success": True})
    monkeypatch.setattr(freecad_runtime, "save_runtime_metadata", lambda data, metadata_path=None: str(tmp_path / "meta.json"))

    result = freecad_runtime.ensure_managed_runtime(
        install_if_missing=False,
        runtime_root=str(runtime_root),
    )

    assert result["success"] is True
    assert result["installed"] is False
    assert result["runtime"]["freecad_cmd"] == str(freecad_cmd)
