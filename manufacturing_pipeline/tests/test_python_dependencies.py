from manufacturing_pipeline.core import python_dependencies


def test_missing_host_dependencies_reports_install_command(monkeypatch):
    monkeypatch.setattr(
        python_dependencies.importlib.util,
        "find_spec",
        lambda module: None if module in {"cadquery", "OCP", "shapely"} else object(),
    )

    result = python_dependencies.ensure_host_python_dependencies(install_if_missing=False)

    assert result["success"] is False
    assert "cadquery" in result["missing"]
    assert "shapely" in result["missing"]
    assert result["command"][0] == python_dependencies.sys.executable
    assert "cadquery>=2.4.0" in result["command"]
    assert "cadquery-ocp" in result["command"]
    assert "shapely" in result["command"]


def test_ensure_host_dependencies_installs_when_missing(monkeypatch):
    calls = {"count": 0}

    def fake_find_spec(module):
        if module in {"cadquery", "OCP", "shapely"}:
            return None if calls["count"] == 0 else object()
        return object()

    def fake_run(command, check):
        calls["count"] += 1
        return None

    monkeypatch.setattr(python_dependencies.importlib.util, "find_spec", fake_find_spec)
    monkeypatch.setattr(python_dependencies.subprocess, "run", fake_run)

    result = python_dependencies.ensure_host_python_dependencies(install_if_missing=True)

    assert result["success"] is True
    assert result["installed"] is True
    assert calls["count"] == 1
