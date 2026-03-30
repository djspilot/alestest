import json
import os
import pytest

from manufacturing_pipeline.core.profiler import AnalysisProfiler


def test_profiler_step_timing():
    p = AnalysisProfiler("test.step", 1.0)
    with p.step("Load", 1, 3):
        pass  # instant
    assert len(p.steps) == 1
    assert p.steps[0]["name"] == "Load"
    assert p.steps[0]["elapsed"] >= 0
    assert p.steps[0]["status"] == "OK"


def test_profiler_sub_step():
    p = AnalysisProfiler("test.step", 1.0)
    with p.step("Detect", 1, 1):
        with p.sub_step("Cylindrical"):
            pass
        p.set_sub_count("Cylindrical", 5)
    assert len(p.steps[0]["sub_steps"]) == 1
    assert p.steps[0]["sub_steps"][0]["name"] == "Cylindrical"
    assert p.steps[0]["sub_steps"][0]["count"] == 5


def test_profiler_count():
    p = AnalysisProfiler("test.step", 1.0)
    p.count("faces", 100)
    p.count("holes", 7)
    assert p.counts == {"faces": 100, "holes": 7}


def test_profiler_step_failure():
    p = AnalysisProfiler("test.step", 1.0)
    with pytest.raises(ValueError):
        with p.step("Bad step", 1, 1):
            raise ValueError("boom")
    assert p.steps[0]["status"] == "FAIL"
    assert p.steps[0]["error"] == "boom"


def test_profiler_save_json(tmp_path):
    p = AnalysisProfiler("part.step", 2.5)
    with p.step("Load", 1, 2):
        pass
    with p.step("Detect", 2, 2):
        with p.sub_step("Shaped", count=3):
            pass
    p.count("holes", 3)
    path = p.save_json(str(tmp_path))
    assert os.path.exists(path)
    with open(path) as f:
        data = json.load(f)
    assert data["part_name"] == "part.step"
    assert data["file_size_mb"] == 2.5
    assert len(data["steps"]) == 2
    assert data["counts"]["holes"] == 3


def test_profiler_print_summary(capsys):
    p = AnalysisProfiler("test.step", 1.0)
    with p.step("Load", 1, 1):
        pass
    p.print_summary()
    captured = capsys.readouterr()
    assert "test.step" in captured.out
    assert "Load" in captured.out


def test_profiler_emit_callback():
    events = []
    def callback(event, summary):
        events.append(event)

    p = AnalysisProfiler("test.step", 1.0, event_callback=callback)
    with p.step("Load", 1, 1):
        pass
    # stage_start + stage_end = 2 events
    assert len(events) >= 2
    assert events[0]["type"] == "stage_start"
    assert events[-1]["type"] == "stage_end"


def test_profiler_emit_custom_event():
    events = []
    def callback(event, summary):
        events.append(event)

    p = AnalysisProfiler("test.step", 1.0, event_callback=callback)
    with p.step("Load", 1, 1):
        p.emit("custom_event", "Load", {"key": "val"})
    custom = [e for e in events if e["type"] == "custom_event"]
    assert len(custom) == 1
    assert custom[0]["payload"] == {"key": "val"}


def test_profiler_fmt_time():
    assert AnalysisProfiler._fmt_time(0.5) == "0.50s"
    assert AnalysisProfiler._fmt_time(90.0) == "1m 30s"


def test_profiler_skip_status():
    p = AnalysisProfiler("test.step", 1.0)
    with p.step("Optional", 1, 1) as s:
        s["status"] = "SKIP"
    assert p.steps[0]["status"] == "SKIP"
