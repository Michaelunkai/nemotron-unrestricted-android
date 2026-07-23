import hashlib
import http.server
import json
import pathlib
import subprocess
import tempfile
import threading
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
BROWSER = ROOT / "bin" / "codex-browser-safe"


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/result"):
            body = b"<html><head><title>Result</title></head><body>Verified result</body></html>"
            content_type = "text/html"
        elif self.path == "/file":
            body = b"download-proof"
            content_type = "application/octet-stream"
        else:
            body = b"""<html><head><title>Fixture</title></head><body>
            <form action="/result" method="get"><input id="query" name="q"><button id="go">Go</button></form>
            <a id="file" href="/file">Download</a></body></html>"""
            content_type = "text/html"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join()
        cls.server.server_close()

    def invoke(self, *args):
        result = subprocess.run([str(BROWSER), *args], cwd=ROOT, capture_output=True, text=True, check=False)
        return result, json.loads(result.stdout if result.returncode == 0 else result.stderr)

    def test_fill_submit_wait_evaluate_and_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            actions = root / "actions.json"
            actions.write_text(json.dumps([
                {"action": "fill", "selector": "#query", "value": "hello world"},
                {"action": "submit", "selector": "#go"},
                {"action": "wait", "selector": "body", "timeoutMs": 1000},
            ]), encoding="utf-8")
            result, receipt = self.invoke(
                self.url, "--actions", str(actions), "--expect-text", "Verified result",
                "--eval", "document.title", "--eval", "location.href",
                "--screenshot", str(root / "shot.png"), "--pdf", str(root / "page.pdf"),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(receipt["taskVerified"])
            self.assertEqual(receipt["evaluations"]["document.title"], "Result")
            self.assertIn("q=hello+world", receipt["url"])
            self.assertTrue((root / "shot.png").read_bytes().startswith(b"\x89PNG"))
            self.assertTrue((root / "page.pdf").read_bytes().startswith(b"%PDF"))

    def test_download_hash_and_reject_unsupported_eval(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            actions = root / "actions.json"
            target = root / "proof.bin"
            actions.write_text(json.dumps([
                {"action": "download", "selector": "#file", "path": str(target)},
            ]), encoding="utf-8")
            result, receipt = self.invoke(self.url, "--actions", str(actions))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(receipt["downloads"][0]["sha256"], hashlib.sha256(b"download-proof").hexdigest())
            result, receipt = self.invoke(self.url, "--eval", "alert(1)")
            self.assertEqual(result.returncode, 2)
            self.assertEqual(receipt["error"], "evaluation_not_allowlisted")

    def test_selector_and_url_fail_closed(self):
        result, receipt = self.invoke("https://user:pass@example.com/")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(receipt["error"], "url_credentials_forbidden")
        result, receipt = self.invoke(self.url, "--wait-selector", "body div", "--timeout", "1")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(receipt["error"], "selector_not_supported")


if __name__ == "__main__":
    unittest.main()
