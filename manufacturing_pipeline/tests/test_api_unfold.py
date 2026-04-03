from pathlib import Path

from fastapi.testclient import TestClient

from manufacturing_pipeline.api.app import app
from manufacturing_pipeline.api import routes as routes_module
from manufacturing_pipeline.api.job_manager import JobManager


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
