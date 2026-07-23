import http.server
import pathlib
import runpy
import socket
import sys
import threading
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))
MODULE = runpy.run_path(str(ROOT / "bin/codex-netdiag"), run_name="netdiag_test")


class NetdiagTests(unittest.TestCase):
    def test_host_validation_and_dns_localhost(self):
        self.assertEqual(MODULE["host"]("LOCALHOST"), "localhost")
        with self.assertRaisesRegex(Exception, "host_invalid"):
            MODULE["host"]("bad..host")
        receipt = MODULE["dns"]("localhost")
        self.assertTrue(receipt["reachable"])
        self.assertTrue(receipt["addresses"])

    def test_tcp_open_and_closed_are_both_verified_diagnoses(self):
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen()
        port = server.getsockname()[1]
        try:
            self.assertTrue(MODULE["tcp"]("127.0.0.1", port, 1)["reachable"])
        finally:
            server.close()
        closed = MODULE["tcp"]("127.0.0.1", port, 1)
        self.assertFalse(closed["reachable"])
        self.assertEqual(closed["failureCategory"], "connection_refused")

    def test_https_rejects_credentials_and_plain_http(self):
        for value in ("http://example.com", "https://u:p@example.com"):
            with self.assertRaisesRegex(Exception, "https_url_invalid"):
                MODULE["https"](value, 1)

    def test_route_falls_back_to_validated_android_connectivity_without_identifiers(self):
        receipt = MODULE["android_connectivity_route"](
            "Active default network: 125\n"
            "NetworkAgentInfo{network{125} handle{secret} "
            "nc{[ Transports: WIFI|VPN Capabilities: INTERNET&TRUSTED&VALIDATED&FOREGROUND "
            "Specifier: <SSID=private>]}}"
        )
        self.assertTrue(receipt["defaultRoutePresent"])
        self.assertTrue(receipt["validatedInternet"])
        self.assertEqual(receipt["routeVisibility"], "android-connectivity-fallback")
        self.assertEqual(receipt["routes"][0]["transports"], ["VPN", "WIFI"])
        self.assertNotIn("SSID", str(receipt))
        self.assertNotIn("125", str(receipt))

    def test_socket_route_probe_proves_default_route_without_disclosing_local_ip(self):
        receipt = MODULE["socket_route_receipt"]()
        self.assertTrue(receipt["defaultRoutePresent"])
        self.assertEqual(receipt["routeVisibility"], "kernel-socket-probe")
        self.assertNotIn("localAddress", receipt)


if __name__ == "__main__":
    unittest.main()
