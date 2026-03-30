from types import SimpleNamespace

from manufacturing_pipeline import cli


def test_cli_batch_stops_with_install_command_when_python_deps_missing(monkeypatch, capsys):
    monkeypatch.setattr(cli, "parse_args", lambda: SimpleNamespace(
        file=None,
        analyze=False,
        verbose=False,
        debug=False,
        no_unfold=False,
        no_pdf=False,
        batch=True,
        parallel=1,
        json=False,
        no_cache=True,
        clear_cache=False,
        list=False,
    ))
    monkeypatch.setattr(cli, "find_step_files", lambda search_dir=None: ["demo.step"])
    monkeypatch.setattr(cli, "ensure_host_python_dependencies", lambda install_if_missing=False: {
        "success": False,
        "command": ["/usr/bin/python3", "-m", "pip", "install", "cadquery>=2.4.0", "cadquery-ocp"],
    })
    monkeypatch.setattr(cli, "auto_install_python_dependencies_enabled", lambda: False)

    cli.main()
    output = capsys.readouterr().out

    assert "Missing Python dependencies. Install with:" in output
    assert "cadquery>=2.4.0" in output


def test_cli_single_file_continues_when_python_deps_ok(monkeypatch):
    called = {}

    monkeypatch.setattr(cli, "parse_args", lambda: SimpleNamespace(
        file="demo.step",
        analyze=False,
        verbose=False,
        debug=False,
        no_unfold=False,
        no_pdf=False,
        batch=False,
        parallel=1,
        json=False,
        no_cache=True,
        clear_cache=False,
        list=False,
    ))
    monkeypatch.setattr(cli, "find_step_files", lambda search_dir=None: ["demo.step"])
    monkeypatch.setattr(cli, "resolve_step_file", lambda args, step_files: "demo.step")
    monkeypatch.setattr(cli, "ensure_host_python_dependencies", lambda install_if_missing=False: {"success": True})
    monkeypatch.setattr(cli, "auto_install_python_dependencies_enabled", lambda: False)
    monkeypatch.setattr(cli, "run_quick", lambda step_file, args: called.setdefault("step_file", step_file))

    cli.main()

    assert called["step_file"] == "demo.step"
