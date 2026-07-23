import json
import os
import pathlib
import stat
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "bin" / "codex-research"


def make_command(path, body):
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class ResearchTests(unittest.TestCase):
    def run_research(self, *args, search_body=None, fetch_body=None):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            search = root / "search"
            fetch = root / "fetch"
            make_command(search, search_body or "exit 9\n")
            make_command(fetch, fetch_body or "exit 9\n")
            env = os.environ.copy()
            env.update({
                "NEMOTRON_SEARCH_COMMAND": str(search),
                "NEMOTRON_FETCH_COMMAND": str(fetch),
                "CODEX_RUNTIME_ROOT": str(root / "runtime"),
            })
            result = subprocess.run(
                [str(RESEARCH), *args], cwd=ROOT, env=env,
                capture_output=True, text=True, check=False,
            )
            stream = result.stdout if result.returncode == 0 else result.stderr
            return result, json.loads(stream)

    def test_unwraps_filters_and_deduplicates_provider_redirects(self):
        receipt = {
            "verified": True,
            "results": [
                {"title": "Jobs", "url": "http://duckduckgo.com/l/?uddg=https%3A%2F%2Fdeveloper.android.com%2Fjobs%3Fa%3D1&rut=x"},
                {"title": "Duplicate Jobs", "url": "https://developer.android.com/jobs?a=1#section"},
                {"title": "Wrong host", "url": "https://example.com/jobs"},
                {"title": "Credentials", "url": "https://user:pass@developer.android.com/bad"},
            ],
            "providerAttempts": [{"provider": "fixture", "resultCount": 4}],
        }
        body = "printf '%s\\n' " + repr(json.dumps(receipt)) + "\n"
        result, output = self.run_research(
            "search", "--query", "jobs", "--domain", "developer.android.com",
            "--contains", "jobs", search_body=body,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(output["taskVerified"])
        self.assertEqual(output["filteredResultCount"], 1)
        self.assertEqual(output["results"][0]["url"], "https://developer.android.com/jobs?a=1")
        self.assertEqual(output["provenance"][0]["url"], output["results"][0]["url"])

    def test_rejects_invalid_pagination_and_fetch_credentials(self):
        result, output = self.run_research(
            "search", "--query", "x", "--page", "2", "--per-page", "25",
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(output["error"], "provider_result_window_exceeded")
        result, output = self.run_research("fetch", "https://u:p@example.com/")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(output["error"], "url_invalid")

    def test_fetch_preserves_provenance(self):
        receipt = {
            "verified": True, "finalUrl": "https://example.com/final",
            "status": 200, "contentType": "text/plain", "bytes": 2,
            "text": "ok", "links": [], "attempts": 1,
            "headers": {"retry-after": "3"},
        }
        body = "printf '%s\\n' " + repr(json.dumps(receipt)) + "\n"
        result, output = self.run_research(
            "fetch", "https://example.com/start", fetch_body=body,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(output["taskVerified"])
        self.assertEqual(output["provenance"]["requestedUrl"], "https://example.com/start")
        self.assertEqual(output["provenance"]["retryAfter"], "3")


if __name__ == "__main__":
    unittest.main()
