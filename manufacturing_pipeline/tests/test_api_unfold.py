from pathlib import Path
from xml.etree import ElementTree

from fastapi.testclient import TestClient

from manufacturing_pipeline.api.app import app
from manufacturing_pipeline.api import routes as routes_module
from manufacturing_pipeline.api.job_manager import JobManager
from manufacturing_pipeline.reporting.xml_exporter import _format_float


def test_job_archive_roundtrip_and_default_listing(tmp_path):
    db_path = tmp_path / "api.db"
    test_jobs = JobManager(str(db_path))

    job = test_jobs.create("job-archive", str(tmp_path / "part.step"), file_name="part.step")
    test_jobs.mark_completed(job.job_id, {"file": "part.step", "success": True})

    items, total = test_jobs.list_jobs()
    assert total == 1
    assert items[0]["job_id"] == "job-archive"
    assert items[0]["archived"] is False

    updated = test_jobs.set_archived(job.job_id, True)
    assert updated is not None
    assert updated.archived is True
    assert updated.archived_at is not None

    active_items, active_total = test_jobs.list_jobs()
    assert active_total == 0
    assert active_items == []

    archived_items, archived_total = test_jobs.list_jobs(archived_only=True)
    assert archived_total == 1
    assert archived_items[0]["job_id"] == "job-archive"
    assert archived_items[0]["archived"] is True

    restored = test_jobs.set_archived(job.job_id, False)
    assert restored is not None
    assert restored.archived is False
    assert restored.archived_at is None


def test_archive_endpoints_and_filters(tmp_path, monkeypatch):
    db_path = tmp_path / "api.db"
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()

    test_jobs = JobManager(str(db_path))
    monkeypatch.setattr(routes_module, "jobs", test_jobs)
    monkeypatch.setattr(routes_module, "UPLOAD_DIR", str(upload_dir))

    step_path = upload_dir / "job-archive-api" / "part.step"
    step_path.parent.mkdir(parents=True, exist_ok=True)
    step_path.write_text("ISO-10303-21;")

    job = test_jobs.create("job-archive-api", str(step_path), file_name="part.step")
    test_jobs.mark_completed(job.job_id, {"file": "part.step", "success": True})

    client = TestClient(app)

    archive_response = client.post(f"/api/v1/jobs/{job.job_id}/archive")
    assert archive_response.status_code == 200
    assert archive_response.json()["archived"] is True

    active_list = client.get("/api/v1/jobs")
    assert active_list.status_code == 200
    assert active_list.json()["total"] == 0

    archived_list = client.get("/api/v1/jobs?archived_only=true")
    assert archived_list.status_code == 200
    assert archived_list.json()["total"] == 1
    assert archived_list.json()["items"][0]["job_id"] == job.job_id
    assert archived_list.json()["items"][0]["archived"] is True

    restore_response = client.post(f"/api/v1/jobs/{job.job_id}/restore")
    assert restore_response.status_code == 200
    assert restore_response.json()["archived"] is False

    bulk_archive = client.post("/api/v1/jobs/archive-all")
    assert bulk_archive.status_code == 200
    assert bulk_archive.json()["affected"] == 1


def test_unfold_flow_for_completed_job(tmp_path, monkeypatch):
    db_path = tmp_path / "api.db"
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()

    test_jobs = JobManager(str(db_path))
    monkeypatch.setattr(routes_module, "jobs", test_jobs)
    monkeypatch.setattr(routes_module, "UPLOAD_DIR", str(upload_dir))

    step_path = upload_dir / "job-1" / "part.step"
    step_path.parent.mkdir(parents=True, exist_ok=True)
    step_path.write_text("ISO-10303-21;")

    job = test_jobs.create(
        "job-1",
        str(step_path),
        file_name="part.step",
        file_hash="abc123",
        file_size_bytes=16,
    )
    test_jobs.mark_completed(
        job.job_id,
        {
            "file": "part.step",
            "success": True,
            "category": "GEBOGEN PLAATWERK",
            "part_type": "plaat",
            "thickness": 5.0,
            "production": {"holes_total": 0, "bends_total": 2, "bends_up": 1, "bends_down": 1},
        },
    )

    def fake_run_unfold_to_step(step_file, output_dir, part_name, analysis):
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        flat_step = output_path / f"{part_name}_flat.step"
        dxf = output_path / f"{part_name}_flat.dxf"
        flat_step.write_text("flat-step")
        dxf.write_text("flat-dxf")
        return {
            "success": True,
            "flat_length": 100.0,
            "flat_width": 50.0,
            "fold_lines": 2,
            "raw_fold_lines": 5,
            "bend_line_groups": [
                {"id": 1, "segment_indices": [0, 1]},
                {"id": 2, "segment_indices": [2, 3, 4]},
            ],
            "flat_step_path": str(flat_step),
            "dxf_path": str(dxf),
        }

    monkeypatch.setattr(routes_module, "run_unfold_to_step", fake_run_unfold_to_step)

    client = TestClient(app)

    queue_response = client.post("/api/v1/jobs/job-1/unfold")
    assert queue_response.status_code == 202
    queue_payload = queue_response.json()
    assert queue_payload["status"] in {"queued", "completed"}

    status_response = client.get("/api/v1/jobs/job-1/unfold")
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["status"] == "completed"
    assert status_payload["result"]["raw_fold_lines"] == 5
    assert status_payload["result"]["fold_lines"] == 2
    assert status_payload["result"]["flat_step_url"].endswith("/api/v1/jobs/job-1/unfold/artifacts/flat-step")
    assert status_payload["result"]["dxf_url"].endswith("/api/v1/jobs/job-1/unfold/artifacts/dxf")

    artifact_response = client.get("/api/v1/jobs/job-1/unfold/artifacts/flat-step")
    assert artifact_response.status_code == 200
    assert artifact_response.content == b"flat-step"


def test_unfold_status_derives_merged_lines_from_groups(tmp_path, monkeypatch):
    db_path = tmp_path / "api.db"
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()

    test_jobs = JobManager(str(db_path))
    monkeypatch.setattr(routes_module, "jobs", test_jobs)
    monkeypatch.setattr(routes_module, "UPLOAD_DIR", str(upload_dir))

    step_path = upload_dir / "job-2" / "part.step"
    step_path.parent.mkdir(parents=True, exist_ok=True)
    step_path.write_text("ISO-10303-21;")

    job = test_jobs.create("job-2", str(step_path), file_name="part.step")
    test_jobs.mark_completed(job.job_id, {"file": "part.step", "success": True})
    test_jobs.mark_unfold_completed(
        job.job_id,
        {
            "success": True,
            "flat_length": 1903.0,
            "flat_width": 199.16,
            "fold_lines": 0,
            "raw_fold_lines": None,
            "fold_details": [],
            "bends_logical": [],
            "bend_line_segments": [
                {"index": 0, "axis": "Y", "axis_span": [1733.0, 1968.0], "center": [-44.791, 1850.5, 5.0]},
                {"index": 1, "axis": "Y", "axis_span": [65.0, 1453.0], "center": [-44.791, 759.0, 5.0]},
                {"index": 2, "axis": "Y", "axis_span": [1483.0, 1703.0], "center": [-44.791, 1593.0, 5.0]},
                {"index": 3, "axis": "Y", "axis_span": [979.0, 1968.0], "center": [44.791, 1473.5, 5.0]},
                {"index": 4, "axis": "Y", "axis_span": [65.0, 902.5], "center": [44.791, 483.75, 5.0]},
            ],
            "bend_line_groups": [
                {"id": 1, "axis": "Y", "segment_indices": [0, 1, 2]},
                {"id": 2, "axis": "Y", "segment_indices": [3, 4]},
            ],
        },
    )

    client = TestClient(app)
    response = client.get("/api/v1/jobs/job-2/unfold")
    assert response.status_code == 200
    payload = response.json()["result"]
    assert payload["fold_lines"] == 2
    assert payload["raw_fold_lines"] == 5
    assert len(payload["fold_details"]) == 2
    assert payload["fold_details"][0]["segment_indices"] == [1, 2, 3]


def test_unfold_status_filters_zero_length_segments_before_counting(tmp_path, monkeypatch):
    db_path = tmp_path / "api.db"
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()

    test_jobs = JobManager(str(db_path))
    monkeypatch.setattr(routes_module, "jobs", test_jobs)
    monkeypatch.setattr(routes_module, "UPLOAD_DIR", str(upload_dir))

    step_path = upload_dir / "job-filter" / "part.step"
    step_path.parent.mkdir(parents=True, exist_ok=True)
    step_path.write_text("ISO-10303-21;")


def test_job_json_and_xml_share_core_sheet_fields(tmp_path, monkeypatch):
    db_path = tmp_path / "api.db"
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()

    test_jobs = JobManager(str(db_path))
    monkeypatch.setattr(routes_module, "jobs", test_jobs)
    monkeypatch.setattr(routes_module, "UPLOAD_DIR", str(upload_dir))

    step_path = upload_dir / "job-consistency" / "part.step"
    step_path.parent.mkdir(parents=True, exist_ok=True)
    step_path.write_text("ISO-10303-21;")

    job = test_jobs.create("job-consistency", str(step_path), file_name="part.step")
    test_jobs.mark_completed(
        job.job_id,
        {
            "file": "part.step",
            "success": True,
            "category": "SHEET_METAL",
            "part_type": "plaat",
            "thickness": 2.0,
            "dimensions": {"length": 100.0, "width": 50.0, "height": 2.0},
            "production": {"holes_total": 0, "bends_total": 0, "bends_up": 0, "bends_down": 0},
            "flat_dimensions": {"length": 90.0, "width": 45.0},
            "sheet_metrics": {
                "volume": 0.0,
                "top_area": 0.0,
                "area_no_holes": 0.0,
                "total_area": 0.0,
                "outer_contour": 0.0,
                "total_contour": 0.0,
            },
            "visuals": {
                "holes": {
                    "items": [
                        {
                            "id": "hole-1",
                            "status": "accepted",
                            "type": "round",
                            "diameter": 10.0,
                            "perimeter": 31.4159265359,
                        }
                    ]
                },
                "unfold": {
                    "success": True,
                    "flat_length": 90.0,
                    "flat_width": 45.0,
                    "fold_lines": 2,
                    "bends_logical": [
                        {"id": 1, "type": "up", "angle": 90.0, "radius": 5.0},
                        {"id": 2, "type": "down", "angle": 45.0, "radius": 3.0},
                    ],
                },
            },
        },
    )
    test_jobs.mark_unfold_completed(
        job.job_id,
        {
            "success": True,
            "flat_length": 120.0,
            "flat_width": 55.0,
            "fold_lines": 2,
            "bends_logical": [
                {"id": 1, "type": "up", "angle": 0.0, "radius": 0.0},
                {"id": 2, "type": "down", "angle": 0.0, "radius": 0.0},
            ],
        },
    )

    client = TestClient(app)

    json_response = client.get(f"/api/v1/jobs/{job.job_id}")
    assert json_response.status_code == 200
    json_result = json_response.json()["result"]

    assert json_result["production"]["bends_total"] == 2
    assert json_result["production"]["bends_up"] == 1
    assert json_result["production"]["bends_down"] == 1
    assert json_result["flat_dimensions"] == {"length": 120.0, "width": 55.0}
    assert json_result["visuals"]["unfold"]["bends_logical"] == [
        {"id": 1, "type": "up", "angle": 90.0, "radius": 5.0},
        {"id": 2, "type": "down", "angle": 45.0, "radius": 3.0},
    ]

    xml_response = client.get(f"/api/v1/jobs/{job.job_id}?format=xml")
    assert xml_response.status_code == 200

    xml_root = ElementTree.fromstring(xml_response.content)
    calc = xml_root.find("CalculationResult")
    assert calc is not None

    sheet_metrics = json_result["sheet_metrics"]
    bends = json_result["visuals"]["unfold"]["bends_logical"]
    expected_fields = {
        "Sheet_NrBends": str(json_result["production"]["bends_total"]),
        "Sheet_BendAngles": "_".join(_format_float(bend["angle"]) for bend in bends),
        "Sheet_BendInnerRadii": "_".join(_format_float(bend["radius"]) for bend in bends),
        "Sheet_FlatX": _format_float(json_result["flat_dimensions"]["length"]),
        "Sheet_FlatY": _format_float(json_result["flat_dimensions"]["width"]),
        "Sheet_Volume": _format_float(sheet_metrics["volume"]),
        "Sheet_TopArea": _format_float(sheet_metrics["top_area"]),
        "Sheet_AreaNoHoles": _format_float(sheet_metrics["area_no_holes"]),
        "Sheet_TotalArea": _format_float(sheet_metrics["total_area"]),
        "Sheet_OuterContour": _format_float(sheet_metrics["outer_contour"]),
        "Sheet_TotalContour": _format_float(sheet_metrics["total_contour"]),
    }

    for field_name, expected_value in expected_fields.items():
        assert calc.findtext(field_name, "") == expected_value

    job = test_jobs.create("job-filter", str(step_path), file_name="part.step")
    test_jobs.mark_completed(job.job_id, {"file": "part.step", "success": True})
    test_jobs.mark_unfold_completed(
        job.job_id,
        {
            "success": True,
            "flat_length": 300.0,
            "flat_width": 80.0,
            "bend_line_segments": [
                {"index": 0, "axis": "X", "axis_span": [0.0, 40.0], "center": [20.0, 10.0, 0.0], "length": 40.0},
                {"index": 1, "axis": "X", "axis_span": [190.0, 240.0], "center": [215.0, 10.0, 0.0], "length": 50.0},
                {"index": 2, "axis": "X", "axis_span": [120.0, 120.0], "center": [120.0, 10.0, 0.0], "length": 0.0},
            ],
            "bends_logical": [
                {"type": "up", "angle": 90.0, "radius": 1.0},
                {"type": "up", "angle": 90.0, "radius": 1.0},
                {"type": "up", "angle": 90.0, "radius": 1.0},
            ],
        },
    )

    client = TestClient(app)
    response = client.get("/api/v1/jobs/job-filter/unfold")
    assert response.status_code == 200
    payload = response.json()["result"]
    assert payload["raw_fold_lines"] == 3
    assert payload["fold_lines"] == 1
    assert len(payload["fold_details"]) == 1


def test_assembly_part_routes_expose_step_and_unfold_artifacts(tmp_path, monkeypatch):
    db_path = tmp_path / "api.db"
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()

    test_jobs = JobManager(str(db_path))
    monkeypatch.setattr(routes_module, "jobs", test_jobs)
    monkeypatch.setattr(routes_module, "UPLOAD_DIR", str(upload_dir))

    assembly_path = upload_dir / "job-3" / "assembly.step"
    assembly_path.parent.mkdir(parents=True, exist_ok=True)
    assembly_path.write_text("ISO-10303-21;")

    job = test_jobs.create("job-3", str(assembly_path), file_name="assembly.step")
    test_jobs.mark_completed(
        job.job_id,
        {
            "file": "assembly.step",
            "success": True,
            "is_assembly": True,
            "solid_count": 2,
            "parts": [
                {
                    "file": "part_a.step",
                    "success": True,
                    "solid_name": "Part A",
                    "solid_index": 0,
                    "category": "PLAAT",
                    "thickness": 2.0,
                    "production": {"holes_total": 1, "bends_total": 2},
                },
                {
                    "file": "part_b.step",
                    "success": True,
                    "solid_name": "Part B",
                    "solid_index": 1,
                    "category": "PLAAT",
                    "thickness": 3.0,
                    "production": {"holes_total": 0, "bends_total": 1},
                },
            ],
        },
    )

    def fake_extract_solids_to_temp_files(_step_file):
        tmp_dir = tmp_path / "split"
        tmp_dir.mkdir(exist_ok=True)
        part_a = tmp_dir / "Part_A.step"
        part_b = tmp_dir / "Part_B.step"
        part_a.write_text("part-a-step")
        part_b.write_text("part-b-step")
        return [
            {"name": "Part A", "path": str(part_a), "index": 0, "tmp_dir": str(tmp_dir)},
            {"name": "Part B", "path": str(part_b), "index": 1, "tmp_dir": str(tmp_dir)},
        ]

    def fake_run_unfold_to_step(step_file, output_dir, part_name, analysis):
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        flat_step = output_path / f"{part_name}_flat.step"
        dxf = output_path / f"{part_name}_flat.dxf"
        flat_step.write_text(f"flat:{Path(step_file).name}")
        dxf.write_text("flat-dxf")
        return {
            "success": True,
            "flat_length": 42.0,
            "flat_width": 24.0,
            "fold_lines": analysis.bend_count_erp,
            "raw_fold_lines": analysis.bend_count_erp,
            "flat_step_path": str(flat_step),
            "dxf_path": str(dxf),
        }

    monkeypatch.setattr(routes_module, "extract_solids_to_temp_files", fake_extract_solids_to_temp_files)
    monkeypatch.setattr(routes_module, "run_unfold_to_step", fake_run_unfold_to_step)

    client = TestClient(app)

    part_response = client.get("/api/v1/jobs/job-3/parts/1")
    assert part_response.status_code == 200
    assert part_response.json()["result"]["solid_name"] == "Part B"

    step_response = client.get("/api/v1/jobs/job-3/parts/1/step")
    assert step_response.status_code == 200
    assert step_response.content == b"part-b-step"

    unfold_response = client.get("/api/v1/jobs/job-3/parts/1/unfold")
    assert unfold_response.status_code == 200
    unfold_payload = unfold_response.json()["result"]
    assert unfold_payload["fold_lines"] == 1
    assert unfold_payload["flat_step_url"].endswith("/api/v1/jobs/job-3/parts/1/unfold/artifacts/flat-step")

    artifact_response = client.get("/api/v1/jobs/job-3/parts/1/unfold/artifacts/flat-step")
    assert artifact_response.status_code == 200
    assert artifact_response.content == b"flat:02_Part_B.step"

    step_zip_response = client.get("/api/v1/jobs/job-3/downloads/part-steps")
    assert step_zip_response.status_code == 200

    unfold_zip_response = client.get("/api/v1/jobs/job-3/downloads/part-unfolds")
    assert unfold_zip_response.status_code == 200
