from fastapi.testclient import TestClient

from manufacturing_pipeline.api.app import app


def test_viewer_default_step_endpoint_serves_repo_relative_sample():
    client = TestClient(app)

    response = client.get("/api/v1/viewer/default-step")

    assert response.status_code == 200
    assert response.headers["content-disposition"].endswith('filename="nieuwmodel.step"')
    assert response.content.startswith(b"ISO-10303-21;")
