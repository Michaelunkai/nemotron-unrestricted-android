import pathlib
import runpy
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))
MODULE = runpy.run_path(str(ROOT / "bin/codex-inventory"), run_name="inventory_test")


class InventoryTests(unittest.TestCase):
    def test_gateway_identity_keeps_only_safe_stable_fields(self):
        receipt = {
            "verified": True, "taskVerified": True,
            "computer": "PC", "user": "user", "tailnetAddress": "100.64.0.2",
            "port": 18767, "gateway": "READY", "companion": "READY",
            "elevated": True, "stdout": "must-not-persist", "token": "must-not-persist",
        }
        identity = MODULE["gateway_identity"](receipt)
        self.assertNotIn("stdout", identity)
        self.assertNotIn("token", identity)
        self.assertEqual(identity["computer"], "PC")

    def test_unverified_gateway_is_refused(self):
        with self.assertRaisesRegex(RuntimeError, "gateway_identity_unverified"):
            MODULE["gateway_identity"]({"verified": False, "taskVerified": False})


if __name__ == "__main__":
    unittest.main()
