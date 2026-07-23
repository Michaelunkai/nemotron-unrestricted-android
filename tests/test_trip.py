import contextlib
import io
import json
import pathlib
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE = runpy.run_path(str(ROOT / "bin" / "codex-trip"), run_name="trip_test")


class TripTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        MODULE["create_pack"].__globals__["WORKSPACE"] = self.root / "workspace" / "trips"
        MODULE["create_pack"].__globals__["STATE"] = self.root / "state" / "trips"
        MODULE["verify_receipt"].__globals__["WORKSPACE"] = self.root / "workspace" / "trips"
        MODULE["verify_receipt"].__globals__["STATE"] = self.root / "state" / "trips"
        self.spec_path = self.root / "trip-spec.json"
        self.spec_path.write_text(json.dumps({
            "schemaVersion": 1,
            "name": "Paris summer trip",
            "origin": "Berlin, Germany",
            "destination": "Paris, France",
            "startDate": "2026-08-10",
            "endDate": "2026-08-14",
            "travelers": 2,
            "transportModes": ["rail", "transit", "walking"],
            "interests": ["museums", "food"],
            "accessibilityNeeds": ["step-free transit"],
        }), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_pack_contains_encoded_maps_calendar_queries_and_hash_receipt(self):
        spec = MODULE["load_spec"](self.spec_path)
        record, receipt = MODULE["create_pack"](spec, False, 8)
        pack = pathlib.Path(record["pack"])
        self.assertEqual({path.name for path in pack.iterdir()}, {
            "actions.json", "itinerary.md", "research.json", "trip.ics", "trip.json",
        })
        actions = json.loads((pack / "actions.json").read_text())
        self.assertIn("api=1", actions["directionsUrl"])
        self.assertNotIn(" ", actions["directionsUrl"])
        self.assertIn("DTSTART;VALUE=DATE:20260810", (pack / "trip.ics").read_text())
        self.assertGreaterEqual(len(json.loads((pack / "research.json").read_text())["queries"]), 6)
        verified = MODULE["verify_receipt"](receipt)
        self.assertEqual(verified["tripSha256"], record["tripSha256"])

    def test_research_records_current_search_evidence_and_progress(self):
        spec = MODULE["load_spec"](self.spec_path)
        completed = subprocess.CompletedProcess([], 0, "source title https://example.test\n", "")
        progress = io.StringIO()
        with mock.patch("subprocess.run", return_value=completed) as called, contextlib.redirect_stderr(progress):
            record, _ = MODULE["create_pack"](spec, True, 2)
        self.assertTrue(record["researchComplete"])
        self.assertEqual(called.call_count, 2)
        self.assertIn("researching current source set 1 of 2", progress.getvalue())

    def test_invalid_date_range_and_unknown_fields_fail_closed(self):
        bad = json.loads(self.spec_path.read_text())
        bad["endDate"] = "2026-08-01"
        self.spec_path.write_text(json.dumps(bad))
        with self.assertRaisesRegex(Exception, "trip_date_range_invalid"):
            MODULE["load_spec"](self.spec_path)
        bad["endDate"] = "2026-08-14"
        bad["paymentCard"] = "not accepted"
        self.spec_path.write_text(json.dumps(bad))
        with self.assertRaisesRegex(Exception, "trip_schema_invalid"):
            MODULE["load_spec"](self.spec_path)

    def test_changed_pack_refuses_verified_readback(self):
        spec = MODULE["load_spec"](self.spec_path)
        record, receipt = MODULE["create_pack"](spec, False, 8)
        pathlib.Path(record["pack"], "itinerary.md").write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(Exception, "trip_pack_changed"):
            MODULE["verify_receipt"](receipt)


if __name__ == "__main__":
    unittest.main()
