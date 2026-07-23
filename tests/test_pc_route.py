import json
import pathlib
import runpy
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))
from nemotron_automation import AutomationState


class PcRouteTests(unittest.TestCase):
    def setUp(self):
        self.module = runpy.run_path(str(ROOT / "bin/codex-pc-route"), run_name="pc_route_test")
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT / "build")
        self.state = AutomationState(pathlib.Path(self.temporary.name) / "state")

    def tearDown(self):
        self.temporary.cleanup()

    def test_hysteresis_keeps_healthy_prior_route_within_twenty_percent(self):
        routes = [
            {"route": "gateway", "eligible": True, "latencyMs": 110},
            {"route": "ssh", "eligible": True, "latencyMs": 100},
        ]
        self.state.cache_set("pc_routes", "selected", {"route": "gateway"}, 300)
        selected = self.module["select"](routes, self.state)
        self.assertEqual(selected["route"], "gateway")
        routes[0]["latencyMs"] = 130
        selected = self.module["select"](routes, self.state)
        self.assertEqual(selected["route"], "ssh")

    def test_unconfigured_routes_are_explicitly_ineligible(self):
        for function in ("ssh_route", "https_route", "smb_route"):
            result = self.module[function](None)
            self.assertFalse(result["eligible"])
            self.assertEqual(result["reason"], "not_configured")


if __name__ == "__main__":
    unittest.main()
