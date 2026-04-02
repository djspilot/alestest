from manufacturing_pipeline.core import freecad_runtime
from manufacturing_pipeline.core.config import SystemConfig
from manufacturing_pipeline.core.freecad_vendor import vendor_sheetmetal_root


def test_managed_runtime_root_prefers_env(monkeypatch):
    monkeypatch.setenv("FREECAD_RUNTIME_ROOT", "/tmp/custom-freecad-runtime")
    assert freecad_runtime.managed_runtime_root() == "/tmp/custom-freecad-runtime"


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


def test_install_sheetmetal_source_uses_vendored_copy():
    result = freecad_runtime._install_sheetmetal_source({}, freecad_runtime.DEFAULT_SHEETMETAL_REPO, False)

    assert result["success"] is True
    assert result["sheetmetal_dest"] == vendor_sheetmetal_root()


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


def test_ensure_managed_runtime_repairs_existing_runtime(monkeypatch, tmp_path):
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

    verify_calls = {"count": 0}
    install_calls = {"count": 0}

    def fake_verify(info):
        verify_calls["count"] += 1
        return {"success": verify_calls["count"] > 1, "error": "missing SheetMetalUnfolder"}

    def fake_install(runtime_info, sheetmetal_repo, update_sheetmetal):
        install_calls["count"] += 1
        return {"success": True}

    monkeypatch.setattr(freecad_runtime, "_verify_runtime", fake_verify)
    monkeypatch.setattr(freecad_runtime, "_install_sheetmetal_source", fake_install)
    monkeypatch.setattr(freecad_runtime, "save_runtime_metadata", lambda data, metadata_path=None: str(tmp_path / "meta.json"))

    result = freecad_runtime.ensure_managed_runtime(
        install_if_missing=True,
        runtime_root=str(runtime_root),
    )

    assert result["success"] is True
    assert result["installed"] is False
    assert verify_calls["count"] == 2
    assert install_calls["count"] == 1


def test_bootstrap_package_manager_disabled_by_default(monkeypatch):
    monkeypatch.delenv("FREECAD_BOOTSTRAP_PACKAGE_MANAGER", raising=False)
    result = freecad_runtime.bootstrap_package_manager()
    assert result["success"] is False
    assert "FREECAD_BOOTSTRAP_PACKAGE_MANAGER=1" in result["error"]
    assert result["command"]


def test_ensure_managed_runtime_uses_bootstrapped_package_manager(monkeypatch, tmp_path):
    runtime_root = tmp_path / "freecad"
    calls = {"commands": []}

    monkeypatch.setattr(freecad_runtime, "choose_package_manager", lambda: "")
    monkeypatch.setattr(
        freecad_runtime,
        "bootstrap_package_manager",
        lambda: {"success": True, "package_manager": "/tmp/micromamba", "command": ["bootstrap"]},
    )
    monkeypatch.setattr(
        freecad_runtime,
        "_run_command",
        lambda command, capture_output=False, text=True: calls["commands"].append(command),
    )
    monkeypatch.setattr(
        freecad_runtime,
        "_install_sheetmetal_source",
        lambda runtime_info, sheetmetal_repo, update_sheetmetal: {"success": True},
    )
    monkeypatch.setattr(freecad_runtime, "_verify_runtime", lambda info: {"success": True, "stage": "verified"})
    monkeypatch.setattr(freecad_runtime, "save_runtime_metadata", lambda data, metadata_path=None: str(tmp_path / "meta.json"))

    result = freecad_runtime.ensure_managed_runtime(
        install_if_missing=True,
        runtime_root=str(runtime_root),
    )

    assert result["success"] is True
    assert result["installed"] is True
    assert "bootstrapped_package_manager" in result["actions"]
    assert calls["commands"]
    assert calls["commands"][0][0] == "/tmp/micromamba"


def test_ensure_managed_runtime_force_reinstall_removes_existing_runtime(monkeypatch, tmp_path):
    runtime_root = tmp_path / "freecad"
    runtime_root.mkdir(parents=True)
    stale_file = runtime_root / "stale.txt"
    stale_file.write_text("old")

    metadata_path = tmp_path / "freecad_runtime.json"
    metadata_path.write_text("{}")

    commands = []

    monkeypatch.setattr(freecad_runtime, "managed_runtime_metadata_path", lambda project_root=None: str(metadata_path))
    monkeypatch.setattr(freecad_runtime, "choose_package_manager", lambda: "/tmp/micromamba")
    monkeypatch.setattr(
        freecad_runtime,
        "_run_command",
        lambda command, capture_output=False, text=True: commands.append(command),
    )
    monkeypatch.setattr(
        freecad_runtime,
        "_install_sheetmetal_source",
        lambda runtime_info, sheetmetal_repo, update_sheetmetal: {"success": True},
    )
    monkeypatch.setattr(freecad_runtime, "_verify_runtime", lambda info: {"success": True, "stage": "verified"})
    monkeypatch.setattr(freecad_runtime, "save_runtime_metadata", lambda data, metadata_path=None: str(tmp_path / "meta.json"))

    result = freecad_runtime.ensure_managed_runtime(
        install_if_missing=True,
        runtime_root=str(runtime_root),
        force_reinstall=True,
    )

    assert result["success"] is True
    assert result["installed"] is True
    assert "removed_existing_runtime" in result["actions"]
    assert "removed_runtime_metadata" in result["actions"]
    assert commands
    assert commands[0][0] == "/tmp/micromamba"
    assert stale_file.exists() is False


def test_ensure_managed_runtime_does_not_precreate_prefix(monkeypatch, tmp_path):
    runtime_root = tmp_path / "freecad"
    observed = {"exists_before_create": None}

    def fake_run_command(command, capture_output=False, text=True):
        observed["exists_before_create"] = runtime_root.exists()
        return None

    monkeypatch.setattr(freecad_runtime, "choose_package_manager", lambda: "/tmp/micromamba")
    monkeypatch.setattr(freecad_runtime, "_run_command", fake_run_command)
    monkeypatch.setattr(
        freecad_runtime,
        "_install_sheetmetal_source",
        lambda runtime_info, sheetmetal_repo, update_sheetmetal: {"success": True},
    )
    monkeypatch.setattr(freecad_runtime, "_verify_runtime", lambda info: {"success": True, "stage": "verified"})
    monkeypatch.setattr(freecad_runtime, "save_runtime_metadata", lambda data, metadata_path=None: str(tmp_path / "meta.json"))

    result = freecad_runtime.ensure_managed_runtime(
        install_if_missing=True,
        runtime_root=str(runtime_root),
    )

    assert result["success"] is True
    assert observed["exists_before_create"] is False


def test_ensure_managed_runtime_force_reinstall_falls_back_when_remove_fails(monkeypatch, tmp_path):
    runtime_root = tmp_path / "freecad"
    runtime_root.mkdir(parents=True)
    metadata_path = tmp_path / "freecad_runtime.json"
    metadata_path.write_text("{}")
    commands = []

    monkeypatch.setattr(freecad_runtime, "managed_runtime_metadata_path", lambda project_root=None: str(metadata_path))
    monkeypatch.setattr(freecad_runtime, "choose_package_manager", lambda: "/tmp/micromamba")
    monkeypatch.setattr(freecad_runtime, "_remove_tree_if_exists", lambda path: "WinError 5")
    monkeypatch.setattr(
        freecad_runtime,
        "_run_command",
        lambda command, capture_output=False, text=True: commands.append(command),
    )
    monkeypatch.setattr(
        freecad_runtime,
        "_install_sheetmetal_source",
        lambda runtime_info, sheetmetal_repo, update_sheetmetal: {"success": True},
    )
    monkeypatch.setattr(freecad_runtime, "_verify_runtime", lambda info: {"success": True, "stage": "verified"})
    monkeypatch.setattr(freecad_runtime, "save_runtime_metadata", lambda data, metadata_path=None: str(tmp_path / "meta.json"))

    result = freecad_runtime.ensure_managed_runtime(
        install_if_missing=True,
        runtime_root=str(runtime_root),
        force_reinstall=True,
    )

    assert result["success"] is True
    assert "failed_to_remove_existing_runtime" in result["actions"]
    assert any(action.startswith("fallback_runtime_root=") for action in result["actions"])
    assert commands
    assert commands[0][4].endswith("freecad_alt")


def test_ensure_managed_runtime_retries_create_with_fallback_prefix(monkeypatch, tmp_path):
    runtime_root = tmp_path / "freecad"
    calls = {"count": 0, "commands": []}

    def fake_run_command(command, capture_output=False, text=True):
        calls["count"] += 1
        calls["commands"].append(command)
        if calls["count"] == 1:
            raise RuntimeError("critical libmamba Non-conda folder exists at prefix - aborting.")
        return None

    monkeypatch.setattr(freecad_runtime, "choose_package_manager", lambda: "/tmp/micromamba")
    monkeypatch.setattr(freecad_runtime, "_run_command", fake_run_command)
    monkeypatch.setattr(
        freecad_runtime,
        "_install_sheetmetal_source",
        lambda runtime_info, sheetmetal_repo, update_sheetmetal: {"success": True},
    )
    monkeypatch.setattr(freecad_runtime, "_verify_runtime", lambda info: {"success": True, "stage": "verified"})
    monkeypatch.setattr(freecad_runtime, "save_runtime_metadata", lambda data, metadata_path=None: str(tmp_path / "meta.json"))

    result = freecad_runtime.ensure_managed_runtime(
        install_if_missing=True,
        runtime_root=str(runtime_root),
    )

    assert result["success"] is True
    assert calls["count"] == 2
    assert calls["commands"][0][4].endswith("freecad")
    assert calls["commands"][1][4].endswith("freecad_alt")
    assert "create_runtime_failed_for_primary_prefix" in result["actions"]


def test_doctor_runtime_reports_verify_failure(monkeypatch, tmp_path):
    runtime_root = tmp_path / "freecad"
    monkeypatch.setattr(freecad_runtime, "managed_runtime_root", lambda project_root=None: str(runtime_root))
    monkeypatch.setattr(
        freecad_runtime,
        "diagnose_package_manager",
        lambda: {"chosen": "", "discovered": [], "auto_bootstrap_enabled": False},
    )

    result = freecad_runtime.doctor_runtime(runtime_root=str(runtime_root))

    assert result["platform"]
    assert result["runtime_root"] == str(runtime_root)
    assert result["verify"]["success"] is False
    assert result["verify"]["stage"] == "resolve_freecad-runtime"
