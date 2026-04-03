"""Tests voor de API in lite modus (DISABLE_STAGES=unfold, FREECAD_AUTO_INSTALL=0).

Verifieert dat de API correct en graceful werkt op de VPS zonder FreeCAD.
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Health endpoint — werkt altijd, ook zonder FreeCAD
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    @pytest.fixture(autouse=True)
    def _client(self):
        from manufacturing_pipeline.api.app import app
        self.client = TestClient(app)

    def test_health_returns_200(self):
        response = self.client.get("/api/v1/health")
        assert response.status_code == 200

    def test_health_no_auth_required(self):
        """Health check mag nooit achter auth zitten — monitoring tools hebben geen API key."""
        response = self.client.get("/api/v1/health")
        assert response.status_code != 401

    def test_health_returns_json(self):
        response = self.client.get("/api/v1/health")
        data = response.json()
        assert isinstance(data, dict)

    def test_api_root_returns_something(self):
        response = self.client.get("/")
        assert response.status_code in (200, 404)


# ---------------------------------------------------------------------------
# Auth middleware
# ---------------------------------------------------------------------------

class TestAuthMiddleware:
    @pytest.fixture(autouse=True)
    def _client_with_key(self):
        with patch.dict(os.environ, {"API_KEYS": "test-key-abc"}):
            # Re-importeer config zodat de env var opgepikt wordt
            import importlib
            import manufacturing_pipeline.api.config as cfg
            importlib.reload(cfg)
            from manufacturing_pipeline.api.app import app
            self.client = TestClient(app)
        yield
        # Herstel config
        import manufacturing_pipeline.api.config as cfg
        importlib.reload(cfg)

    def test_api_endpoint_without_key_returns_401_when_keys_set(self):
        # Patch de al-geladen API_KEYS lijst direct in de app module
        from manufacturing_pipeline.api import app as app_module
        with patch.object(app_module, "API_KEYS", ["secret-key"]):
            from manufacturing_pipeline.api.app import app
            client = TestClient(app)
            response = client.get("/api/v1/stats")
            assert response.status_code == 401

    def test_health_never_requires_auth(self):
        """Health mag nooit 401 geven, ook niet als API_KEYS ingesteld is."""
        with patch.dict(os.environ, {"API_KEYS": "secret-key"}):
            import importlib
            import manufacturing_pipeline.api.config as cfg
            importlib.reload(cfg)
            from manufacturing_pipeline.api.app import app
            client = TestClient(app)
            response = client.get("/api/v1/health")
            assert response.status_code == 200


# ---------------------------------------------------------------------------
# Config: DISABLE_STAGES parsing
# ---------------------------------------------------------------------------

class TestDisableStagesConfig:
    def test_unfold_in_disable_stages_when_env_set(self):
        with patch.dict(os.environ, {"DISABLE_STAGES": "unfold"}):
            import importlib
            import manufacturing_pipeline.api.config as cfg
            importlib.reload(cfg)
            assert "unfold" in cfg.DISABLE_STAGES

    def test_disable_stages_merged_with_defaults(self):
        with patch.dict(os.environ, {"DISABLE_STAGES": "unfold"}):
            import importlib
            import manufacturing_pipeline.api.config as cfg
            importlib.reload(cfg)
            # Defaults (profile_router, detect_holes_pre_unfold) moeten ook aanwezig blijven
            assert "profile_router" in cfg.DISABLE_STAGES
            assert "unfold" in cfg.DISABLE_STAGES

    def test_empty_disable_stages_is_valid(self):
        with patch.dict(os.environ, {"DISABLE_STAGES": ""}):
            import importlib
            import manufacturing_pipeline.api.config as cfg
            importlib.reload(cfg)
            assert isinstance(cfg.DISABLE_STAGES, set)

    def test_invalid_stage_key_rejected_by_api(self):
        from manufacturing_pipeline.api.app import app
        client = TestClient(app)
        response = client.post(
            "/api/v1/analyze",
            files={"file": ("test.step", b"ISO-10303-21;", "application/step")},
            params={"disable_stages": "nonexistent_stage"},
        )
        assert response.status_code == 400
        assert "Invalid disable_stages" in response.json()["detail"]

    def test_unfold_stage_key_is_valid(self):
        from manufacturing_pipeline.api import config
        assert "unfold" in config.VALID_STAGE_KEYS

    def test_aag_stage_key_is_valid(self):
        from manufacturing_pipeline.api import config
        assert "aag" in config.VALID_STAGE_KEYS


# ---------------------------------------------------------------------------
# File upload validatie
# ---------------------------------------------------------------------------

class TestFileUploadValidation:
    @pytest.fixture(autouse=True)
    def _client(self):
        from manufacturing_pipeline.api.app import app
        self.client = TestClient(app)

    def test_wrong_extension_returns_400(self):
        response = self.client.post(
            "/api/v1/analyze",
            files={"file": ("test.pdf", b"%PDF-1.4", "application/pdf")},
        )
        assert response.status_code == 400
        assert "Invalid file type" in response.json()["detail"]

    def test_step_extension_accepted(self):
        """Een geldig STEP bestand wordt geaccepteerd (ook al faalt de analyse daarna)."""
        response = self.client.post(
            "/api/v1/analyze",
            files={"file": ("test.step", b"ISO-10303-21;", "application/step")},
        )
        # 202 (queued) of 500 (analyse fout) zijn beide OK — niet 400
        assert response.status_code in (202, 422, 500)

    def test_stp_extension_accepted(self):
        response = self.client.post(
            "/api/v1/analyze",
            files={"file": ("test.stp", b"ISO-10303-21;", "application/step")},
        )
        assert response.status_code in (202, 422, 500)

    def test_missing_file_returns_422(self):
        response = self.client.post("/api/v1/analyze")
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Job endpoints
# ---------------------------------------------------------------------------

class TestJobEndpoints:
    @pytest.fixture(autouse=True)
    def _client(self):
        from manufacturing_pipeline.api.app import app
        self.client = TestClient(app)

    def test_unknown_job_returns_404(self):
        response = self.client.get("/api/v1/jobs/nonexistent-job-id-xyz")
        assert response.status_code == 404

    def test_list_jobs_returns_200(self):
        response = self.client.get("/api/v1/jobs")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    def test_list_jobs_pagination_params(self):
        response = self.client.get("/api/v1/jobs?limit=5&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 5
        assert data["offset"] == 0

    def test_stats_endpoint_returns_200(self):
        response = self.client.get("/api/v1/stats")
        assert response.status_code == 200
