"""Platform-focused tests for robust Windows FreeCAD/unfold behavior."""

from pathlib import PureWindowsPath
from unittest.mock import patch

from manufacturing_pipeline.analysis import freecad_unfold
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


def test_windows_unfold_prefers_subprocess_mode_by_default() -> None:
    """Windows auto mode should prefer the external FreeCADCmd route."""
    with patch("manufacturing_pipeline.analysis.freecad_unfold.sys.platform", "win32"):
        assert freecad_unfold._should_prefer_freecadcmd() is True


def test_macos_unfold_prefers_subprocess_mode_by_default() -> None:
    """macOS should also prefer the external FreeCADCmd route in auto mode."""
    with patch("manufacturing_pipeline.analysis.freecad_unfold.sys.platform", "darwin"):
        assert freecad_unfold._should_prefer_freecadcmd() is True


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

    def fake_run(cmd, capture_output, text, timeout):  # type: ignore[no-untyped-def]
        commands.append(cmd)
        return DummyCompletedProcess()

    with patch("manufacturing_pipeline.core.runtime_unfold.subprocess.run", side_effect=fake_run):
        result = runtime_unfold.run_unfold(str(step_file), str(output_dir), "part", DummyAnalysis())

    assert result["success"] is True
    assert commands
    assert commands[0][0] == runtime_unfold.HOST_PYTHON
    assert commands[0][1].endswith("freecad_unfold.py")
