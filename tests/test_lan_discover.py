import importlib.util
from importlib.machinery import SourceFileLoader
import pathlib
import sys
import types
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))
SOURCE = ROOT / "bin/codex-lan-discover"
SPEC = importlib.util.spec_from_loader("codex_lan_discover", SourceFileLoader("codex_lan_discover", str(SOURCE)))
LAN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LAN)


class LanDiscoverTests(unittest.TestCase):
    def test_scope_is_bounded_and_local(self):
        self.assertEqual(str(LAN.parse_scope("192.168.1.10/24")), "192.168.1.0/24")
        with self.assertRaises(ValueError):
            LAN.parse_scope("10.0.0.0/8")
        with self.assertRaises(ValueError):
            LAN.parse_scope("8.8.8.0/24")

    def test_tcp_ports_are_explicit_unique_and_bounded(self):
        self.assertEqual(LAN.parse_ports("443,22,443"), [22, 443])
        with self.assertRaises(ValueError):
            LAN.parse_ports("0")
        with self.assertRaises(ValueError):
            LAN.parse_ports(",".join(str(value) for value in range(1, 34)))

    def test_neighbor_read_is_passive_and_structured(self):
        bridge = types.SimpleNamespace(
            remote_status=0,
            stdout="192.168.1.2 dev wlan0 lladdr aa:bb:cc:dd:ee:ff REACHABLE\n",
        )
        with mock.patch.object(LAN, "run_rish", return_value=bridge) as run:
            receipt, status = LAN.neighbor_receipt()
        self.assertEqual(status, 0)
        self.assertTrue(receipt["verified"])
        self.assertEqual(receipt["items"][0]["address"], "192.168.1.2")
        self.assertEqual(run.call_args.args[0], "ip neigh show")

    def test_pc_route_requires_an_exact_verified_gateway_receipt(self):
        completed = types.SimpleNamespace(
            returncode=0,
            stdout='{"ok":true,"verified":true,"verificationBasis":"exact-diagnostics-receipt"}',
            stderr="",
        )
        with mock.patch.object(LAN.subprocess, "run", return_value=completed):
            receipt, status = LAN.pc_receipt()
        self.assertEqual(status, 0)
        self.assertTrue(receipt["verified"])
        self.assertIn("available and verified", receipt["message"])


if __name__ == "__main__":
    unittest.main()
