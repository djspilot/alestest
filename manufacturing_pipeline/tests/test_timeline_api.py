"""Tests for timeline replay API functionality."""

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from manufacturing_pipeline.api.analysis_service import _build_timeline
from manufacturing_pipeline.api.routes import get_job_timeline


class DummyRouteCategory:
    value = "plaat"


class DummyRouteResult:
    category = DummyRouteCategory()
    profile_label = "PLAT_STAAL"
    confidence = 0.98
    method = "rule"
    variant = None
    reasoning = "Detected as flat plate"


class DummyAnalysis:
    route_result = DummyRouteResult()
    unfold_result = {
        "success": False,
        "error": "Unfold failed",
        "error_details": [{"message": "No valid base face"}],
    }


class TestTimelineBuild(unittest.TestCase):
    def test_build_timeline_from_timing_data(self):
        result = {
            "file": "part.step",
            "production": {
                "bends_total": 3,
                "bends_up": 2,
                "bends_down": 1,
            },
        }
        timing_data = {
            "part_name": "part.step",
            "total_elapsed": 12.5,
            "steps": [
                {
                    "name": "Load STEP",
                    "num": 1,
                    "total": 7,
                    "elapsed": 1.5,
                    "status": "OK",
                    "error": None,
                    "sub_steps": [],
                },
                {
                    "name": "Detect holes",
                    "num": 6,
                    "total": 7,
                    "elapsed": 2.0,
                    "status": "OK",
                    "error": None,
                    "sub_steps": [
                        {"name": "Cylindrical", "elapsed": 0.5, "count": 2},
                        {"name": "Shaped", "elapsed": 1.0, "count": 1},
                    ],
                },
            ],
        }

        events, summary = _build_timeline(
            result=result,
            analysis=DummyAnalysis(),
            total_holes=3,
            timing_data=timing_data,
        )

        self.assertIsNotNone(summary)
        self.assertEqual(summary["step_count"], 2)
        self.assertEqual(summary["part_name"], "part.step")
        self.assertGreater(len(events), 0)

        event_types = {e["type"] for e in events}
        self.assertIn("stage_start", event_types)
        self.assertIn("stage_end", event_types)
        self.assertIn("classification_decision", event_types)
        self.assertIn("holes_detected", event_types)
        self.assertIn("bends_detected", event_types)
        self.assertIn("unfold_failed", event_types)


class TestTimelineRoute(unittest.TestCase):
    def test_get_job_timeline_processing_job_uses_live_progress(self):
        job = SimpleNamespace(
            job_id="job-live",
            status="processing",
            progress_summary={
                "total_elapsed_seconds": 1.2,
                "event_count": 2,
                "step_count": 1,
                "part_name": "demo.step",
                "analysis_started_at": "2026-03-24T10:00:00+00:00",
                "active_stage": "Load STEP",
                "active_stage_started_at": "2026-03-24T10:00:00+00:00",
                "active_stage_elapsed_seconds": 1.2,
                "completed_step_count": 0,
                "total_steps_hint": 7,
            },
            progress_events=[
                {
                    "type": "stage_start",
                    "stage": "Load STEP",
                    "timestamp_ms": 0,
                    "status": "START",
                    "payload": {"num": 1, "total": 7},
                }
            ],
            result=None,
        )

        with patch("manufacturing_pipeline.api.routes.jobs.get", return_value=job):
            response = asyncio.run(get_job_timeline("job-live"))

        self.assertEqual(response.job_id, "job-live")
        self.assertEqual(response.status, "processing")
        self.assertEqual(len(response.events), 1)
        self.assertEqual(response.events[0].stage, "Load STEP")
        self.assertEqual(response.summary.active_stage, "Load STEP")

    def test_get_job_timeline_completed_job(self):
        job = SimpleNamespace(
            job_id="job-1",
            status="completed",
            result={
                "timeline_summary": {
                    "total_elapsed_seconds": 5.2,
                    "event_count": 2,
                    "step_count": 1,
                    "part_name": "demo.step",
                },
                "timeline": [
                    {
                        "type": "stage_start",
                        "stage": "Load STEP",
                        "timestamp_ms": 0,
                        "status": "START",
                        "payload": {},
                    },
                    {
                        "type": "stage_end",
                        "stage": "Load STEP",
                        "timestamp_ms": 600,
                        "status": "OK",
                        "payload": {"elapsed_seconds": 0.6},
                    },
                ],
            },
        )

        with patch("manufacturing_pipeline.api.routes.jobs.get", return_value=job):
            response = asyncio.run(get_job_timeline("job-1"))

        self.assertEqual(response.job_id, "job-1")
        self.assertEqual(response.status, "completed")
        self.assertEqual(len(response.events), 2)
        self.assertEqual(response.summary.part_name, "demo.step")


if __name__ == "__main__":
    unittest.main()
