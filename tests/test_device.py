import pathlib
import runpy
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))
MODULE = runpy.run_path(str(ROOT / "bin/codex-device"), run_name="device_registry_test")


class DeviceTests(unittest.TestCase):
    def test_identity_hashes_fingerprint_and_keeps_safe_fields(self):
        values = {
            "manufacturer": "Samsung", "model": "Galaxy S22", "sdk": "36",
            "securityPatch": "2026-07-01", "fingerprint": "secret-ish-stable-fingerprint",
        }
        identity = MODULE["identity_from_properties"](values)
        self.assertEqual(identity["sdk"], 36)
        self.assertNotIn("fingerprint", identity)
        self.assertEqual(len(identity["fingerprintSha256"]), 64)

    def test_identity_and_inventory_parsers_fail_closed(self):
        with self.assertRaisesRegex(Exception, "device_identity_incomplete"):
            MODULE["identity_from_properties"]({
                "manufacturer": "", "model": "x", "sdk": "36", "securityPatch": "", "fingerprint": "x",
            })
        self.assertEqual(
            MODULE["parse_lines"]("package:com.example.a\nnoise\npackage:com.example.a\npackage:com.example.b\n", "package:"),
            ["com.example.a", "com.example.b"],
        )

    def test_permission_parser_and_capability_map_are_truthful(self):
        parsed = MODULE["parse_permission_grants"](
            "  android.permission.CAMERA: granted=true, flags=[ USER_SET ]\n"
            "  android.permission.RECORD_AUDIO: granted=false, flags=[ USER_SET ]\n"
            "  unrelated\n"
        )
        self.assertTrue(parsed["android.permission.CAMERA"])
        self.assertFalse(parsed["android.permission.RECORD_AUDIO"])
        self.assertIn("camera", MODULE["CAPABILITY_PERMISSIONS"])
        self.assertIn("android.permission.ACCESS_FINE_LOCATION", MODULE["CAPABILITY_PERMISSIONS"]["location"])


if __name__ == "__main__":
    unittest.main()
