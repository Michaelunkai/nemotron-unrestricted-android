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


if __name__ == "__main__":
    unittest.main()
