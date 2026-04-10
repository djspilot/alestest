"""Helpers for executing the full manufacturing pipeline on the VPS API."""

import json
import os
import subprocess
import time
from pathlib import Path
from urllib.parse import urlencode

from manufacturing_pipeline.core.paths import PROJECT_ROOT
from manufacturing_pipeline.reporting.xml_exporter import export_to_xml


def _load_shape_for_cut_features(path: str):
    from manufacturing_pipeline.analysis.step_processing import load_step_file

    shape = load_step_file(path)
    if hasattr(shape, "val"):
        try:
            return shape.val().wrapped
        except Exception:
            return shape.val()
    return shape


def _build_sheet_hole_semantics(step_file: str, output_dir: str, result: dict) -> dict | None:
    category = str(result.get("category") or "").upper()
    if category not in {"PLAAT (VLAK)", "GEBOGEN PLAATWERK", "SHEET_METAL"}:
        return None

    # Keep VPS/XML semantics aligned with the generic cut_features ISO rules.
    # Do not add diameter-specific exceptions in this enrichment path.

    try:
        from manufacturing_pipeline.analysis.cut_features import extract_cut_features_for_sheet
    except Exception:
        return None

    try:
        solid = _load_shape_for_cut_features(step_file)
    except Exception:
        return None

    unfold_result = None
    flat_step_path = os.path.join(output_dir, f"{_safe_stem(step_file)}_flat.step")
    if os.path.exists(flat_step_path):
        try:
            flat_shape = _load_shape_for_cut_features(flat_step_path)
            unfold_result = {"success": True, "flat_pattern": flat_shape}
        except Exception:
            unfold_result = None

    try:
        cut_features = extract_cut_features_for_sheet(
            solid=solid,
            unfold_result=unfold_result,
            part_classification="plaat",
        )
    except Exception:
        return None

    if cut_features is None:
        return None

    return {
        "source": getattr(cut_features, "source", None),
        "threaded_holes": int(getattr(cut_features, "threaded_holes", 0) or 0),
        "countersunk_holes": int(getattr(cut_features, "countersunk_holes", 0) or 0),
        "countersunk_angles": list(getattr(cut_features, "countersunk_angles", []) or []),
        "nr_holes": int(getattr(cut_features, "nr_holes", 0) or 0),
    }


def pipeline_vps_mode() -> str:
    explicit = os.getenv("PIPELINE_VPS_MODE", "").strip().lower()
    if explicit:
        return explicit
    if os.getenv("PYTEST_CURRENT_TEST"):
        return "off"
    # Avoid recursive self-calls when the code runs inside the API server itself.
    if os.getenv("RUNNING_IN_API", "").strip().lower() in {"1", "true", "yes", "on"}:
        return "off"
    # Backward-compat guard in environments that still provide API_KEYS.
    if os.getenv("API_KEYS", "").strip():
        return "off"
    return "always" if os.path.exists(os.path.join(PROJECT_ROOT, ".vps.env")) else "off"


def pipeline_vps_enabled() -> bool:
    return pipeline_vps_mode() not in {"off", "0", "false", "local", "disabled"}


def _load_dotenv_file(path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path or not os.path.exists(path):
        return values
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for raw in handle:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key:
                    values[key] = value
    except Exception:
        return {}
    return values


def _resolve_vps_api_config() -> tuple[str | None, str | None]:
    domain = os.getenv("VPS_DOMAIN_API", "").strip()
    api_key = os.getenv("API_KEY", "").strip()
    if domain and api_key:
        return domain, api_key

    dotenv = _load_dotenv_file(os.path.join(PROJECT_ROOT, ".vps.env"))
    domain = domain or str(dotenv.get("VPS_DOMAIN_API", "")).strip()
    api_key = api_key or str(dotenv.get("API_KEY", "")).strip()
    if not domain or not api_key:
        return None, None
    return domain, api_key


def _normalize_vps_url(domain: str, path: str, query: dict | None = None) -> str:
    base = domain.strip()
    if base.startswith("http://") or base.startswith("https://"):
        root = base.rstrip("/")
    else:
        root = f"https://{base.rstrip('/')}"
    path_part = path if path.startswith("/") else f"/{path}"
    query_part = f"?{urlencode(query)}" if query else ""
    return f"{root}{path_part}{query_part}"


def _run_curl(cmd: list[str], timeout_seconds: int) -> tuple[int, str, str]:
    completed = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=max(20, int(timeout_seconds)),
        check=False,
    )
    return completed.returncode, completed.stdout or "", completed.stderr or ""


def _curl_json(
    url: str,
    api_key: str,
    *,
    method: str = "GET",
    form_file: str | None = None,
    timeout_seconds: int = 60,
) -> dict:
    cmd = [
        "curl",
        "--max-time",
        str(max(20, int(timeout_seconds))),
        "-sS",
        "-H",
        f"X-API-Key: {api_key}",
    ]
    if method.upper() != "GET":
        cmd.extend(["-X", method.upper()])
    if form_file:
        cmd.extend(["-F", f"file=@{form_file}"])
    cmd.append(url)

    returncode, stdout, stderr = _run_curl(cmd, timeout_seconds + 10)
    if returncode != 0:
        raise RuntimeError(f"VPS API curl error ({returncode}): {(stderr or stdout).strip()[:300]}")
    try:
        return json.loads((stdout or "").strip() or "{}")
    except Exception as exc:
        raise RuntimeError(f"VPS API gaf geen geldige JSON terug: {(stdout or '').strip()[:300]}") from exc


def _curl_download(url: str, api_key: str, output_path: str, timeout_seconds: int = 120) -> bool:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    cmd = [
        "curl",
        "--max-time",
        str(max(20, int(timeout_seconds))),
        "-sS",
        "-H",
        f"X-API-Key: {api_key}",
        "-o",
        output_path,
        url,
    ]
    returncode, _stdout, _stderr = _run_curl(cmd, timeout_seconds + 10)
    return returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0


def _compute_pipeline_timeout_sec(step_file: str) -> int:
    try:
        size_mb = os.path.getsize(step_file) / (1024 * 1024)
    except OSError:
        size_mb = 0.0
    return max(300, min(3600, int(300 + (size_mb * 120))))


def _safe_stem(path: str, fallback: str = "result") -> str:
    stem = os.path.splitext(os.path.basename(path))[0].strip() or fallback
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in stem)
    return cleaned or fallback


def run_pipeline_analysis_via_vps(
    step_file: str,
    output_dir: str,
    *,
    use_aag: bool = True,
    disable_stages: set[str] | None = None,
    force: bool = False,
    poll_timeout_seconds: int | None = None,
) -> dict:
    domain, api_key = _resolve_vps_api_config()
    if not domain or not api_key:
        return {
            "success": False,
            "error": "VPS pipeline geconfigureerd maar VPS_DOMAIN_API/API_KEY ontbreken",
        }

    disable_stages = set(disable_stages or set())
    timeout_seconds = poll_timeout_seconds or _compute_pipeline_timeout_sec(step_file)
    query = {
        "force": "true" if force else "false",
        "aag": "true" if use_aag else "false",
    }
    if disable_stages:
        query["disable_stages"] = ",".join(sorted(disable_stages))

    analyze_url = _normalize_vps_url(domain, "/api/v1/analyze", query)
    analyze_payload = _curl_json(
        analyze_url,
        api_key,
        method="POST",
        form_file=step_file,
        timeout_seconds=max(180, timeout_seconds),
    )
    job_id = str(analyze_payload.get("job_id") or "").strip()
    if not job_id:
        return {"success": False, "error": f"VPS analyze gaf geen job_id terug: {analyze_payload}"}

    status_url = _normalize_vps_url(domain, f"/api/v1/jobs/{job_id}")
    deadline = time.time() + timeout_seconds
    status_payload = None
    while time.time() < deadline:
        status_payload = _curl_json(status_url, api_key, method="GET", timeout_seconds=60)
        status = str(status_payload.get("status") or "").lower()
        if status in {"completed", "failed", "cancelled"}:
            break
        time.sleep(2)

    if not status_payload:
        return {"success": False, "error": "VPS pipeline polling gaf geen status terug", "job_id": job_id}

    status = str(status_payload.get("status") or "").lower()
    if status != "completed":
        return {
            "success": False,
            "error": str(status_payload.get("error") or f"VPS pipeline status: {status or 'unknown'}"),
            "job_id": job_id,
            "status_payload": status_payload,
            "reused_existing": bool(analyze_payload.get("reused_existing")),
        }

    result = dict(status_payload.get("result") or {})
    if not result:
        return {
            "success": False,
            "error": "VPS pipeline gaf geen result payload terug",
            "job_id": job_id,
            "status_payload": status_payload,
            "reused_existing": bool(analyze_payload.get("reused_existing")),
        }

    sheet_hole_semantics = _build_sheet_hole_semantics(step_file, output_dir, result)
    if sheet_hole_semantics:
        result["sheet_hole_semantics"] = sheet_hole_semantics

    os.makedirs(output_dir, exist_ok=True)
    stem = _safe_stem(step_file)
    metadata_path = os.path.join(output_dir, f"{stem}_vps_job.json")
    with open(metadata_path, "w", encoding="utf-8") as handle:
        json.dump(status_payload, handle, indent=2, ensure_ascii=False)

    xml_path = os.path.join(output_dir, f"{stem}.xml")
    downloaded_xml = False
    try:
        export_to_xml(result, Path(xml_path))
        downloaded_xml = os.path.exists(xml_path) and os.path.getsize(xml_path) > 0
    except Exception:
        xml_url = _normalize_vps_url(domain, f"/api/v1/jobs/{job_id}/downloads/total-xml")
        downloaded_xml = _curl_download(xml_url, api_key, xml_path, timeout_seconds=120)

    part_xml_zip_path = None
    if result.get("is_assembly"):
        candidate_path = os.path.join(output_dir, f"{stem}_xml.zip")
        zip_url = _normalize_vps_url(domain, f"/api/v1/jobs/{job_id}/downloads/part-xmls")
        if _curl_download(zip_url, api_key, candidate_path, timeout_seconds=120):
            part_xml_zip_path = candidate_path

    return {
        "success": bool(result.get("success", True)),
        "job_id": job_id,
        "result": result,
        "status_payload": status_payload,
        "metadata_path": metadata_path,
        "xml_path": xml_path if downloaded_xml else None,
        "part_xml_zip_path": part_xml_zip_path,
        "reused_existing": bool(analyze_payload.get("reused_existing")),
    }
