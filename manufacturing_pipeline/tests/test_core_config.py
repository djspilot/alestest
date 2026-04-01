import json
import os
import tempfile
import pytest

from manufacturing_pipeline.core.config import (
    SystemConfig,
    ModuleConfig,
    PricingConfig,
    MaterialPricesConfig,
    CostColumnsConfig,
    PipelineConfig,
    MODULE_GROUPS,
    MODULE_NAMES,
    create_default_config,
    create_minimal_config,
    apply_module_toggles,
    _freecad_root_candidates,
    _is_valid_freecad_root,
    diagnose_freecad_setup,
)


# ---- SystemConfig ----

def test_system_config_default_freecad_path():
    cfg = SystemConfig()
    assert isinstance(cfg.freecad_path, str)


def test_system_config_from_env(monkeypatch):
    monkeypatch.setenv("FREECAD_PATH", "/fake/freecad")
    cfg = SystemConfig.from_env()
    assert cfg.freecad_path == "/fake/freecad"


def test_system_config_from_env_missing(monkeypatch):
    monkeypatch.delenv("FREECAD_PATH", raising=False)
    cfg = SystemConfig.from_env()
    assert isinstance(cfg.freecad_path, str)


def test_freecad_root_candidates_linux():
    candidates = _freecad_root_candidates(platform="linux")
    assert any("/usr" in c for c in candidates)


def test_freecad_root_candidates_darwin():
    candidates = _freecad_root_candidates(platform="darwin")
    assert any("FreeCAD.app" in c for c in candidates)


def test_freecad_root_candidates_windows():
    candidates = _freecad_root_candidates(platform="win32")
    assert any("FreeCAD" in c for c in candidates)


def test_is_valid_freecad_root_accepts_mac_app_with_freecadcmd(tmp_path):
    app_root = tmp_path / "FreeCAD.app"
    cmd_path = app_root / "Contents" / "MacOS" / "FreeCADCmd"
    cmd_path.parent.mkdir(parents=True)
    cmd_path.write_text("")

    assert _is_valid_freecad_root(str(app_root), platform="darwin") is True


def test_is_valid_freecad_root_rejects_incomplete_runtime(tmp_path):
    runtime_root = tmp_path / "freecad"
    runtime_root.mkdir()

    assert _is_valid_freecad_root(str(runtime_root), platform="darwin") is False


def test_diagnose_freecad_setup_reports_missing_paths(monkeypatch):
    monkeypatch.setenv("FREECAD_PATH", "/missing/freecad")
    monkeypatch.delenv("FREECAD_PYTHON", raising=False)
    monkeypatch.delenv("FREECAD_CMD", raising=False)
    monkeypatch.setenv("FREECAD_AUTO_INSTALL", "0")

    info = diagnose_freecad_setup(platform="darwin")

    assert info["freecad_path"] == "/missing/freecad"
    assert info["freecad_path_valid"] is False
    assert info["freecad_python_exists"] is False
    assert info["freecad_cmd_exists"] is False
    assert info["recommendations"]


def test_system_config_to_dict():
    cfg = SystemConfig(freecad_path="/test")
    d = cfg.to_dict()
    assert d["freecad_path"] == "/test"
    assert "freecad_cmd" in d


def test_system_config_from_dict():
    cfg = SystemConfig.from_dict({"freecad_path": "/custom"})
    assert cfg.freecad_path == "/custom"


# ---- ModuleConfig ----

def test_module_config_defaults_all_enabled():
    cfg = ModuleConfig()
    enabled = cfg.get_enabled_modules()
    assert "geometry" in enabled
    assert "holes" in enabled


def test_module_config_disabled_list():
    cfg = ModuleConfig()
    cfg.geometry = False
    disabled = cfg.get_disabled_modules()
    assert "geometry" in disabled


def test_module_config_roundtrip():
    cfg = ModuleConfig()
    cfg.holes = False
    d = cfg.to_dict()
    cfg2 = ModuleConfig.from_dict(d)
    assert cfg2.holes is False
    assert cfg2.geometry is True


def test_module_config_from_dict_ignores_unknown():
    cfg = ModuleConfig.from_dict({"geometry": True, "nonexistent_field": True})
    assert cfg.geometry is True


# ---- PricingConfig ----

def test_pricing_config_defaults():
    cfg = PricingConfig()
    assert cfg.cnc_draaien_klein == 55.0
    assert cfg.laser_snijden == 70.0


def test_pricing_config_roundtrip():
    cfg = PricingConfig(cnc_draaien_klein=100.0)
    d = cfg.to_dict()
    cfg2 = PricingConfig.from_dict(d)
    assert cfg2.cnc_draaien_klein == 100.0


# ---- MaterialPricesConfig ----

def test_material_prices_get_price():
    cfg = MaterialPricesConfig()
    assert cfg.get_price("steel_s235") == 1.20
    assert cfg.get_price("nonexistent") == 1.50  # fallback


def test_material_prices_roundtrip():
    cfg = MaterialPricesConfig(steel_s235=2.0)
    d = cfg.to_dict()
    cfg2 = MaterialPricesConfig.from_dict(d)
    assert cfg2.steel_s235 == 2.0


# ---- CostColumnsConfig ----

def test_cost_columns_enabled():
    cfg = CostColumnsConfig()
    enabled = cfg.get_enabled_columns()
    assert "snijden" in enabled


def test_cost_columns_disable():
    cfg = CostColumnsConfig(snijden=False)
    enabled = cfg.get_enabled_columns()
    assert "snijden" not in enabled


# ---- PipelineConfig ----

def test_pipeline_config_defaults():
    cfg = create_default_config("test.step")
    assert cfg.step_file == "test.step"
    assert cfg.modules.geometry is True


def test_pipeline_config_save_load(tmp_path):
    cfg = create_default_config("test.step")
    cfg.material = "steel_304"
    path = str(tmp_path / "config.json")
    cfg.save(path)
    loaded = PipelineConfig.load(path)
    assert loaded.material == "steel_304"
    assert loaded.modules.geometry is True


def test_minimal_config():
    cfg = create_minimal_config("test.step")
    assert cfg.modules.geometry is True
    assert cfg.modules.iso2768_tolerances is False
    assert cfg.modules.cost_estimation is False


# ---- apply_module_toggles ----

def test_toggle_disable_group():
    cfg = ModuleConfig()
    apply_module_toggles(cfg, disable=["iso"])
    assert cfg.iso2768_tolerances is False
    assert cfg.iso286_fits is False
    assert cfg.geometry is True  # untouched


def test_toggle_enable_group():
    cfg = ModuleConfig()
    cfg.iso2768_tolerances = False
    apply_module_toggles(cfg, enable=["iso"])
    assert cfg.iso2768_tolerances is True


def test_toggle_all_group():
    cfg = ModuleConfig()
    apply_module_toggles(cfg, disable=["all"])
    assert cfg.geometry is False
    assert cfg.holes is False


def test_toggle_individual_module():
    cfg = ModuleConfig()
    apply_module_toggles(cfg, disable=["geometry"])
    assert cfg.geometry is False
    assert cfg.holes is True


# ---- MODULE_GROUPS / MODULE_NAMES ----

def test_module_groups_all_is_none():
    assert MODULE_GROUPS["all"] is None


def test_module_names_cover_basic():
    for module in MODULE_GROUPS["basic"]:
        assert module in MODULE_NAMES
