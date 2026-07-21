import importlib.util
import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("nemotron_wifi_report", ROOT / "bin/nemotron_wifi_report.py")
REPORT = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(REPORT)


RAW_SCAN = """    BSSID              Frequency      RSSI           Age(sec)     SSID                                 Flags
  00:11:22:33:44:55       5180    -48(0:-48/1:-52)   2.500      Lab 5 GHz                        [RSN-SAE-CCMP-128][ESS][WPS]
  aa:bb:cc:dd:ee:ff       2412    -71(0:-71/1:-75)   4.000                                        [WPA2-PSK-CCMP-128][ESS]
"""


class WifiReportTests(unittest.TestCase):
    def test_raw_parser_classifies_signal_band_security_and_hidden_network(self):
        networks = REPORT.parse_raw(RAW_SCAN)
        self.assertEqual(len(networks), 2)
        self.assertEqual(networks[0]["ssid"], "Lab 5 GHz")
        self.assertEqual(networks[0]["security"], "WPA3")
        self.assertEqual(networks[0]["band"], "5 GHz")
        self.assertEqual(networks[0]["signal"], "Excellent")
        self.assertTrue(networks[0]["wps"])
        self.assertEqual(networks[1]["ssid"], "Hidden network")

    def test_human_report_is_mobile_readable_and_hides_hardware_addresses(self):
        human = REPORT.render_scan(REPORT.parse_raw(RAW_SCAN), "test service", "rate limited safely")
        self.assertIn("Nearby Wi-Fi", human)
        self.assertIn("2 networks", human)
        self.assertIn("Excellent (-48 dBm) · 5 GHz · WPA3 · WPS", human)
        self.assertIn("rate limited safely", human)
        self.assertNotIn("00:11:22:33:44:55", human)

    def test_json_input_and_control_characters_are_normalized(self):
        data = json.dumps([{"ssid": "Demo\u001b[31m", "bssid": "00:00:00:00:00:01", "frequency_mhz": 2412, "rssi": -65, "capabilities": "[WPA2-PSK][ESS]"}])
        network = REPORT.parse_raw(data)[0]
        self.assertNotIn("\u001b", network["ssid"])
        self.assertEqual(network["security"], "WPA2")


if __name__ == "__main__":
    unittest.main()
