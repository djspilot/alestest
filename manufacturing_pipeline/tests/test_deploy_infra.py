"""Tests die verifiëren dat alle deploy-bestanden correct aanwezig en geldig zijn.

Doel: direct opvangen als een bestand ontbreekt, een verkeerde config heeft,
of een kritieke regel verwijderd is na een refactor.
"""

import os
import stat
import yaml
import pytest

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def _path(*parts):
    return os.path.join(REPO_ROOT, *parts)


# ---------------------------------------------------------------------------
# Dockerfile.api.lite
# ---------------------------------------------------------------------------

class TestDockerfileLite:
    def test_exists(self):
        assert os.path.isfile(_path("Dockerfile.api.lite")), \
            "Dockerfile.api.lite ontbreekt"

    def test_has_freecad_auto_install_disabled(self):
        content = open(_path("Dockerfile.api.lite")).read()
        assert "FREECAD_AUTO_INSTALL=0" in content, \
            "Dockerfile.api.lite moet FREECAD_AUTO_INSTALL=0 bevatten"

    def test_has_disable_stages_unfold(self):
        content = open(_path("Dockerfile.api.lite")).read()
        assert "DISABLE_STAGES=unfold" in content, \
            "Dockerfile.api.lite moet DISABLE_STAGES=unfold bevatten"

    def test_no_freecad_conda_install(self):
        content = open(_path("Dockerfile.api.lite")).read()
        assert "conda-forge" not in content, \
            "Lite Dockerfile mag geen conda-forge/FreeCAD installatie bevatten"
        assert "micromamba" not in content, \
            "Lite Dockerfile mag geen micromamba bevatten"

    def test_exposes_port_8000(self):
        content = open(_path("Dockerfile.api.lite")).read()
        assert "EXPOSE 8000" in content

    def test_uvicorn_cmd(self):
        content = open(_path("Dockerfile.api.lite")).read()
        assert "uvicorn" in content
        assert "manufacturing_pipeline.api.app:app" in content


# ---------------------------------------------------------------------------
# docker-compose.prod.yml
# ---------------------------------------------------------------------------

class TestDockerComposeProd:
    @pytest.fixture(autouse=True)
    def _load(self):
        path = _path("docker-compose.prod.yml")
        assert os.path.isfile(path), "docker-compose.prod.yml ontbreekt"
        with open(path) as f:
            self.compose = yaml.safe_load(f)

    def test_has_api_service(self):
        assert "api" in self.compose["services"]

    def test_api_uses_ghcr_image(self):
        image = self.compose["services"]["api"]["image"]
        assert image.startswith("ghcr.io/"), \
            f"API service moet ghcr.io image gebruiken, niet: {image}"

    def test_api_no_local_build(self):
        assert "build" not in self.compose["services"]["api"], \
            "docker-compose.prod.yml mag geen 'build' sectie bevatten — VPS bouwt nooit zelf"

    def test_api_port_is_localhost_only(self):
        ports = self.compose["services"]["api"].get("ports", [])
        for port in ports:
            assert str(port).startswith("127.0.0.1:"), \
                f"API poort '{port}' moet gebonden zijn aan 127.0.0.1 (niet publiek)"

    def test_api_has_disable_stages_env(self):
        env = self.compose["services"]["api"].get("environment", {})
        env_keys = list(env.keys()) if isinstance(env, dict) else env
        assert "DISABLE_STAGES" in env_keys or any(
            "DISABLE_STAGES" in str(e) for e in env_keys
        ), "DISABLE_STAGES moet in docker-compose.prod.yml environment staan"

    def test_api_has_freecad_auto_install_disabled(self):
        env = self.compose["services"]["api"].get("environment", {})
        assert "FREECAD_AUTO_INSTALL" in env, \
            "FREECAD_AUTO_INSTALL moet in docker-compose.prod.yml environment staan"
        assert str(env["FREECAD_AUTO_INSTALL"]) == "0", \
            f"FREECAD_AUTO_INSTALL moet '0' zijn, niet '{env['FREECAD_AUTO_INSTALL']}'"

    def test_volumes_defined(self):
        assert "volumes" in self.compose, "Geen volumes sectie in docker-compose.prod.yml"
        volumes = self.compose["volumes"]
        assert "ales_uploads" in volumes
        assert "ales_db" in volumes


# ---------------------------------------------------------------------------
# GitHub Actions workflow
# ---------------------------------------------------------------------------

class TestGitHubActionsWorkflow:
    @pytest.fixture(autouse=True)
    def _load(self):
        path = _path(".github", "workflows", "deploy.yml")
        assert os.path.isfile(path), ".github/workflows/deploy.yml ontbreekt"
        with open(path) as f:
            self.workflow = yaml.safe_load(f)

    def test_triggers_on_main_push(self):
        on = self.workflow.get("on", self.workflow.get(True, {}))
        assert "push" in on, "Workflow moet triggeren op push"
        branches = on["push"].get("branches", [])
        assert "main" in branches, "Workflow moet triggeren op main branch"

    def test_has_build_job(self):
        jobs = self.workflow.get("jobs", {})
        assert "build" in jobs, "Workflow moet een 'build' job hebben"

    def test_has_deploy_job(self):
        jobs = self.workflow.get("jobs", {})
        assert "deploy" in jobs, "Workflow moet een 'deploy' job hebben"

    def test_deploy_needs_build(self):
        deploy_job = self.workflow["jobs"]["deploy"]
        needs = deploy_job.get("needs", [])
        if isinstance(needs, str):
            needs = [needs]
        assert "build" in needs, "Deploy job moet wachten op build job"

    def test_build_pushes_to_ghcr(self):
        build_steps = self.workflow["jobs"]["build"]["steps"]
        step_names = [s.get("name", "") for s in build_steps]
        uses_list = [s.get("uses", "") for s in build_steps]
        assert any("ghcr" in n.lower() or "login" in n.lower() for n in step_names) or \
               any("login-action" in u for u in uses_list), \
            "Build job moet inloggen bij ghcr.io"

    def test_deploy_runs_on_vps(self):
        # Deploy via self-hosted runner on the VPS (no SSH action needed —
        # the runner itself is the VPS).
        deploy_job = self.workflow["jobs"]["deploy"]
        runs_on = deploy_job.get("runs-on", "")
        uses_list = [s.get("uses", "") for s in deploy_job.get("steps", [])]
        self_hosted = isinstance(runs_on, list) and "self-hosted" in runs_on
        uses_ssh = any("ssh-action" in u for u in uses_list)
        assert self_hosted or uses_ssh, \
            "Deploy job moet draaien op een self-hosted VPS runner of via ssh-action"

    def test_workflow_dispatch_enabled(self):
        on = self.workflow.get("on", self.workflow.get(True, {}))
        assert "workflow_dispatch" in on, \
            "workflow_dispatch moet aanwezig zijn voor handmatig deployen"


# ---------------------------------------------------------------------------
# Deploy scripts
# ---------------------------------------------------------------------------

class TestDeployScripts:
    def test_deploy_sh_exists(self):
        assert os.path.isfile(_path("deploy", "scripts", "deploy.sh"))

    def test_vps_setup_sh_exists(self):
        assert os.path.isfile(_path("deploy", "scripts", "vps-setup.sh"))

    def test_deploy_sh_references_compose_prod(self):
        content = open(_path("deploy", "scripts", "deploy.sh")).read()
        assert "docker-compose.prod.yml" in content, \
            "deploy.sh moet docker-compose.prod.yml gebruiken"

    def test_deploy_sh_does_pull_not_build(self):
        content = open(_path("deploy", "scripts", "deploy.sh")).read()
        assert "pull" in content, "deploy.sh moet 'docker compose pull' doen"
        assert "build" not in content.replace("# ", "").split("docker login")[0].split("pull")[0], \
            "deploy.sh mag geen 'docker build' aanroepen"

    def test_deploy_sh_has_logging(self):
        content = open(_path("deploy", "scripts", "deploy.sh")).read()
        assert "LOG=" in content or "log()" in content, \
            "deploy.sh moet logging bevatten"

    def test_makefile_exists(self):
        assert os.path.isfile(_path("Makefile"))

    def test_makefile_has_ssh_target(self):
        content = open(_path("Makefile")).read()
        assert "ssh:" in content or ".PHONY: ssh" in content

    def test_makefile_has_deploy_target(self):
        content = open(_path("Makefile")).read()
        assert "deploy:" in content or ".PHONY: deploy" in content

    def test_makefile_has_setup_target(self):
        content = open(_path("Makefile")).read()
        assert "setup:" in content or ".PHONY: setup" in content

    def test_vps_env_example_exists(self):
        assert os.path.isfile(_path(".vps.env.example")), \
            ".vps.env.example ontbreekt"

    def test_vps_env_in_gitignore(self):
        gitignore = open(_path(".gitignore")).read()
        assert ".vps.env" in gitignore, \
            ".vps.env moet in .gitignore staan zodat secrets niet gecommit worden"
