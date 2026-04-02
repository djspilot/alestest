"""Platform-focused tests for robust Windows FreeCAD/unfold behavior."""

from pathlib import PureWindowsPath
from types import SimpleNamespace
from unittest.mock import patch

from manufacturing_pipeline.analysis import freecad_unfold
from manufacturing_pipeline.analysis.sheetmetal import freecad_environment
from manufacturing_pipeline.core.config import SystemConfig
from manufacturing_pipeline.core import runtime_unfold


def test_windows_config_prefers_freecadcmd_when_python_missing() -> None:
    """Windows should fall back to FreeCADCmd when no embedded python exists."""
    freecad_root = r"C:\Program Files\FreeCAD 1.0"
    cmd_path = str(PureWindowsPath(freecad_root) / "bin" / "FreeCADCmd.exe")

    def fake_exists(path: str) -> bool:
        normalized = path.replace("/", "\\")
        return normalized == cmd_path

    with patch("manufacturing_pipeline.core.config.sys.platform", "win32"), \
         patch("manufacturing_pipeline.core.config.os.path.exists", side_effect=fake_exists):
        config = SystemConfig(freecad_path=freecad_root)

        assert config.freecad_python.replace("/", "\\") == cmd_path
        assert config.freecad_cmd.replace("/", "\\") == cmd_path


def test_windows_unfold_prefers_direct_mode_by_default() -> None:
    """Windows auto mode should prefer the in-proc direct route."""
    with patch("manufacturing_pipeline.analysis.freecad_unfold.sys.platform", "win32"):
        assert freecad_unfold._should_prefer_freecadcmd() is False


def test_macos_unfold_prefers_direct_mode_by_default() -> None:
    """macOS should also prefer the in-proc direct route in auto mode."""
    with patch("manufacturing_pipeline.analysis.freecad_unfold.sys.platform", "darwin"):
        assert freecad_unfold._should_prefer_freecadcmd() is False


def test_find_freecadcmd_auto_installs_runtime_when_missing(monkeypatch) -> None:
    captured = {}
    state = {"installed": False}

    monkeypatch.setattr(freecad_environment.freecad_runtime, "auto_install_enabled", lambda: True)

    def fake_configured_runtime():
        if state["installed"]:
            return {"freecad_cmd": "/managed/FreeCADCmd"}
        return {}

    def fake_ensure_runtime(install_if_missing=True):
        captured["install_if_missing"] = install_if_missing
        state["installed"] = True
        return {
            "success": True,
            "runtime": {
                "freecad_cmd": "/managed/FreeCADCmd",
            },
        }

    monkeypatch.setattr(freecad_environment.freecad_runtime, "configured_runtime", fake_configured_runtime)
    monkeypatch.setattr(freecad_environment.freecad_runtime, "ensure_managed_runtime", fake_ensure_runtime)
    monkeypatch.setattr(
        freecad_environment.os.path,
        "exists",
        lambda path: path == "/managed/FreeCADCmd",
    )

    assert freecad_environment._find_freecadcmd_executable() == "/managed/FreeCADCmd"
    assert captured["install_if_missing"] is True


def test_run_unfold_uses_host_python_wrapper(tmp_path) -> None:
    """The legacy unfold wrapper should start with the current Python interpreter."""
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    step_file = tmp_path / "part.step"
    step_file.write_text("ISO-10303-21;")

    commands = []

    class DummyAnalysis:
        flat_length = 0.0
        flat_width = 0.0

    class DummyCompletedProcess:
        def __init__(self) -> None:
            self.returncode = 0
            self.stdout = "\n✓ Ontbuigen geslaagd!\n"
            self.stderr = ""

    def fake_run(cmd, capture_output, text, timeout, env):  # type: ignore[no-untyped-def]
        commands.append((cmd, env))
        return DummyCompletedProcess()

    with patch("manufacturing_pipeline.core.runtime_unfold.subprocess.run", side_effect=fake_run):
        result = runtime_unfold.run_unfold(str(step_file), str(output_dir), "part", DummyAnalysis())

    assert result["success"] is True
    assert commands
    assert commands[0][0][0] == runtime_unfold.HOST_PYTHON
    assert commands[0][0][1].endswith("freecad_unfold.py")
    assert isinstance(commands[0][1], dict)


def test_build_freecad_subprocess_env_includes_managed_runtime_paths(monkeypatch, tmp_path) -> None:
    runtime_root = tmp_path / "runtime"
    lib_dir = runtime_root / "Library" / "bin"
    mingw_dir = runtime_root / "Library" / "mingw-w64" / "bin"
    bin_dir = runtime_root / "bin"
    mod_dir = runtime_root / "Mod"
    for path in (lib_dir, mingw_dir, bin_dir, mod_dir):
        path.mkdir(parents=True, exist_ok=True)

    freecad_python = bin_dir / "python.exe"
    freecad_cmd = bin_dir / "FreeCADCmd.exe"
    freecad_python.write_text("")
    freecad_cmd.write_text("")

    class FakeConfig:
        def __init__(self) -> None:
            self.freecad_path = str(runtime_root)
            self.freecad_python = str(freecad_python)
            self.freecad_cmd = str(freecad_cmd)
            self.freecad_lib = str(lib_dir)
            self.freecad_mod = str(mod_dir)

        @staticmethod
        def _managed_runtime_value(key: str) -> str:
            return str(runtime_root) if key == "runtime_root" else ""

    config = FakeConfig()

    env = runtime_unfold._build_freecad_subprocess_env(config)

    assert env["FREECAD_RUNTIME_ROOT"] == str(runtime_root)
    assert env["FREECAD_PYTHON"] == str(freecad_python)
    assert env["FREECAD_CMD"] == str(freecad_cmd)
    assert env["FREECAD_LIB"] == str(lib_dir)
    assert env["FREECAD_MOD"] == str(mod_dir)
    assert str(lib_dir) in env["PATH"]
    assert str(mingw_dir) in env["PATH"]


def test_resolve_windows_desktop_freecad_config_finds_program_files_install(monkeypatch) -> None:
    freecad_root = r"C:\Program Files\FreeCAD 1.0"

    def fake_exists(path: str) -> bool:
        normalized = path.replace("/", "\\")
        return normalized in {
            rf"{freecad_root}\bin\FreeCADCmd.exe",
            rf"{freecad_root}\bin\python.exe",
            rf"{freecad_root}\Library\bin",
            rf"{freecad_root}\Mod",
        }

    monkeypatch.setattr(runtime_unfold.sys, "platform", "win32")
    monkeypatch.setenv("ProgramFiles", r"C:\Program Files")
    monkeypatch.setenv("ProgramFiles(x86)", r"C:\Program Files (x86)")
    monkeypatch.setattr(runtime_unfold.os.path, "exists", fake_exists)

    config = runtime_unfold._resolve_windows_desktop_freecad_config()

    assert config is not None
    assert config.freecad_path.replace("/", "\\") == freecad_root
    assert config.freecad_cmd.replace("/", "\\").endswith(r"FreeCAD 1.0\bin\FreeCADCmd.exe")


def test_run_unfold_to_step_retries_with_windows_desktop_freecad(monkeypatch, tmp_path) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    step_file = tmp_path / "part.step"
    step_file.write_text("ISO-10303-21;")

    primary = SimpleNamespace(
        freecad_path=r"C:\repo\.runtime\freecad",
        freecad_python=r"C:\repo\.runtime\freecad\python.exe",
        freecad_cmd=r"C:\repo\.runtime\freecad\Library\bin\FreeCADCmd.exe",
        freecad_lib=r"C:\repo\.runtime\freecad\Library\bin",
        freecad_mod=r"C:\repo\.runtime\freecad\Mod",
        _managed_runtime_value=lambda key: r"C:\repo\.runtime\freecad" if key == "runtime_root" else "",
    )
    desktop = SimpleNamespace(
        freecad_path=r"C:\Program Files\FreeCAD 1.0",
        freecad_python=r"C:\Program Files\FreeCAD 1.0\bin\python.exe",
        freecad_cmd=r"C:\Program Files\FreeCAD 1.0\bin\FreeCADCmd.exe",
        freecad_lib=r"C:\Program Files\FreeCAD 1.0\Library\bin",
        freecad_mod=r"C:\Program Files\FreeCAD 1.0\Mod",
        _managed_runtime_value=lambda key: "",
    )

    attempts = []

    def fake_attempt(step, out, part, cfg, runtime_label="managed"):  # type: ignore[no-untyped-def]
        attempts.append((cfg.freecad_cmd, runtime_label))
        if "runtime" in cfg.freecad_path:
            return {"success": False, "error": "managed failed"}
        return {"success": True, "flat_length": 10.0, "flat_width": 5.0}

    monkeypatch.setattr(runtime_unfold.sys, "platform", "win32")
    monkeypatch.setattr(runtime_unfold.SystemConfig, "from_env", staticmethod(lambda: primary))
    monkeypatch.setattr(runtime_unfold, "_resolve_windows_desktop_freecad_config", lambda: desktop)
    monkeypatch.setattr(
        runtime_unfold,
        "_run_direct_unfold_attempt",
        lambda *args, **kwargs: {"success": False, "error": "direct failed"},
    )
    monkeypatch.setattr(
        runtime_unfold,
        "_run_direct_python_subprocess_attempt",
        lambda *args, **kwargs: {"success": False, "error": "direct python failed"},
    )
    monkeypatch.setattr(runtime_unfold, "_run_unfold_subprocess_attempt", fake_attempt)

    result = runtime_unfold.run_unfold_to_step(str(step_file), str(output_dir), "part", object())

    assert result["success"] is True
    assert result["runtime_source"] == "desktop-freecad"
    assert len(attempts) == 2
    assert attempts[0][1] == "direct-freecad-python"
    assert attempts[1][1] == "desktop-freecad"


def test_summarize_unfold_failure_prefers_exception_details() -> None:
    result = {
        "attempts": 4,
        "error_details": [
            {
                "face_idx": 12,
                "stage": "analysis",
                "error_code": 17,
                "message": "Type oppervlak niet ondersteund voor sheet metal",
            },
            {
                "face_idx": 7,
                "stage": "init",
                "error_code": 3,
                "message": "Ongeldige dikte - plaatdikte niet consistent of te complex",
            },
            {
                "face_idx": 3,
                "stage": "exception",
                "error_code": -1,
                "message": "TypeError: unsupported operand type(s) for +: 'NoneType' and 'int'",
            },
        ],
    }

    summary = runtime_unfold._summarize_unfold_failure(result)

    assert "Interne SheetMetal fout tijdens unfold" in summary
    assert "TypeError" in summary
    assert "Type oppervlak niet ondersteund voor sheet metal" in summary


def test_summarize_unfold_failure_lists_readable_causes() -> None:
    result = {
        "attempts": 3,
        "error_details": [
            {
                "face_idx": 12,
                "stage": "analysis",
                "error_code": 17,
                "message": "Type oppervlak niet ondersteund voor sheet metal",
            },
            {
                "face_idx": 7,
                "stage": "init",
                "error_code": 3,
                "message": "Ongeldige dikte - plaatdikte niet consistent of te complex",
            },
        ],
    }

    summary = runtime_unfold._summarize_unfold_failure(result)

    assert "Geen geldige unfold-route gevonden na 3 pogingen" in summary
    assert "Type oppervlak niet ondersteund voor sheet metal" in summary
    assert "Ongeldige dikte - plaatdikte niet consistent of te complex" in summary


def test_run_unfold_to_step_prefers_direct_vendored_unfold(monkeypatch, tmp_path) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    step_file = tmp_path / "part.step"
    step_file.write_text("ISO-10303-21;")

    state = {"direct_calls": 0, "fallback_calls": 0, "exports": []}

    class FlatShape:
        def exportStep(self, path):  # type: ignore[no-untyped-def]
            state["exports"].append(path)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("flat-step")

    def fake_direct(**kwargs):  # type: ignore[no-untyped-def]
        state["direct_calls"] += 1
        return {
            "success": True,
            "flat_shape": FlatShape(),
            "flat_length": 10.0,
            "flat_width": 5.0,
            "bend_angles": [90.0],
            "bend_radii": [1.0],
            "bend_lengths": [20.0],
            "bend_count": 1,
        }

    def fake_subprocess(*args, **kwargs):  # type: ignore[no-untyped-def]
        state["fallback_calls"] += 1
        return {"success": False, "error": "should not be used"}

    monkeypatch.setattr(runtime_unfold.freecad_unfold, "_ensure_freecad_imported", lambda: True)
    monkeypatch.setattr(runtime_unfold.freecad_unfold, "unfold_sheet_metal", fake_direct)
    monkeypatch.setattr(runtime_unfold, "_run_unfold_subprocess_attempt", fake_subprocess)

    result = runtime_unfold.run_unfold_to_step(str(step_file), str(output_dir), "part", object())

    assert result["success"] is True
    assert result["runtime_source"] == "direct-vendored-sheetmetal"
    assert state["direct_calls"] == 1
    assert state["fallback_calls"] == 0
    assert result["flat_step_path"].endswith("part_flat.step")
    assert state["exports"]


def test_run_unfold_to_step_can_skip_host_direct_mode(monkeypatch, tmp_path) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    step_file = tmp_path / "part.step"
    step_file.write_text("ISO-10303-21;")

    calls = {"host_direct": 0, "python_runtime": 0}

    def fake_host_direct(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls["host_direct"] += 1
        return {"success": True}

    def fake_python_runtime(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls["python_runtime"] += 1
        return {"success": True, "runtime_source": "direct-freecad-python"}

    monkeypatch.setenv("FREECAD_UNFOLD_MODE", "direct-python")
    monkeypatch.setattr(runtime_unfold, "_run_direct_unfold_attempt", fake_host_direct)
    monkeypatch.setattr(runtime_unfold, "_run_unfold_subprocess_attempt", fake_python_runtime)

    result = runtime_unfold.run_unfold_to_step(str(step_file), str(output_dir), "part", object())

    assert result["success"] is True
    assert result["runtime_source"] == "direct-freecad-python"
    assert calls["host_direct"] == 0
    assert calls["python_runtime"] == 1


def test_unfolder_variant_mode_defaults_to_auto(monkeypatch) -> None:
    monkeypatch.delenv("FREECAD_UNFOLDER_VARIANT", raising=False)
    assert runtime_unfold._unfolder_variant_mode() == "auto"


def test_unfolder_variant_mode_accepts_new_and_old(monkeypatch) -> None:
    monkeypatch.setenv("FREECAD_UNFOLDER_VARIANT", "new")
    assert runtime_unfold._unfolder_variant_mode() == "new"
    monkeypatch.setenv("FREECAD_UNFOLDER_VARIANT", "old")
    assert runtime_unfold._unfolder_variant_mode() == "old"
