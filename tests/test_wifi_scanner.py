import os
import pathlib
import stat
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCANNER = ROOT / "bin/codex-wifi-scan"
RAW_SCAN = """    BSSID              Frequency      RSSI           Age(sec)     SSID                                 Flags
  00:11:22:33:44:55       5180    -48(0:-48/1:-52)   2.500      Authorized Lab                  [RSN-SAE-CCMP-128][ESS]
"""


class WifiScannerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.bin = self.root / "bin"
        self.state = self.root / "state"
        self.bin.mkdir()
        self.state.mkdir()
        self.rish = self.bin / "rish"
        self.api = self.bin / "termux-wifi-scaninfo"
        self.rish.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' \"$*\" >> \"$NEMOTRON_TEST_RISH_LOG\"\n"
            "[ \"${NEMOTRON_TEST_FAIL:-0}\" = 1 ] && exit 1\n"
            "case \"$*\" in\n"
            "  *list-scan-results*) printf '%s\\n' \"$NEMOTRON_TEST_SCAN\" ;;\n"
            "  *status*) printf '%s\\n' 'Wifi is enabled' 'WifiInfo: SSID: \"Authorized Lab\", IP: /127.0.0.1, Security type: 2, Wi-Fi standard: 11ax, RSSI: -50, Link speed: 100Mbps, Frequency: 5180MHz' ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        self.api.write_text(
            "#!/bin/sh\n"
            "printf 'refresh\\n' >> \"$NEMOTRON_TEST_API_LOG\"\n"
            "printf '[]\\n'\n",
            encoding="utf-8",
        )
        self.rish.chmod(self.rish.stat().st_mode | stat.S_IXUSR)
        self.api.chmod(self.api.stat().st_mode | stat.S_IXUSR)
        self.env = os.environ.copy()
        self.env.update(
            {
                "PATH": f"{self.bin}:/data/data/com.termux/files/usr/bin",
                "NEMOTRON_RISH": str(self.rish),
                "NEMOTRON_WIFI_STATE_DIR": str(self.state),
                "NEMOTRON_WIFI_RETRY_SLEEP": "0",
                "NEMOTRON_TEST_RISH_LOG": str(self.root / "rish.log"),
                "NEMOTRON_TEST_API_LOG": str(self.root / "api.log"),
                "NEMOTRON_TEST_SCAN": RAW_SCAN,
            }
        )

    def tearDown(self):
        self.temp.cleanup()

    def run_scan(self, mode="--refresh", **extra_env):
        env = {**self.env, **extra_env}
        return subprocess.run([str(SCANNER), mode], cwd=ROOT, env=env, text=True, capture_output=True, timeout=10)

    def test_refresh_never_calls_aborting_android_subcommand_and_is_throttled(self):
        outputs = [self.run_scan() for _ in range(5)]
        self.assertTrue(all(result.returncode == 0 for result in outputs), [result.stderr for result in outputs])
        self.assertTrue(all("Nearby Wi-Fi" in result.stdout for result in outputs))
        rish_log = (self.root / "rish.log").read_text(encoding="utf-8")
        self.assertNotIn("start-scan", rish_log)
        self.assertEqual(rish_log.count("list-scan-results"), 5)
        api_log = (self.root / "api.log").read_text(encoding="utf-8")
        self.assertEqual(api_log.count("refresh"), 1)

    def test_last_known_good_cache_survives_three_bounded_read_failures(self):
        primed = self.run_scan("--cached")
        self.assertEqual(primed.returncode, 0, primed.stderr)
        fallback = self.run_scan("--cached", NEMOTRON_TEST_FAIL="1")
        self.assertEqual(fallback.returncode, 0, fallback.stderr)
        self.assertIn("last-known-good cache", fallback.stdout)
        self.assertIn("saved results were used", fallback.stdout)

    def test_connection_output_is_readable_and_does_not_show_mac_fields(self):
        result = self.run_scan("--connection")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Current Wi-Fi connection", result.stdout)
        self.assertIn("Authorized Lab", result.stdout)
        self.assertNotIn("BSSID", result.stdout)


if __name__ == "__main__":
    unittest.main()
