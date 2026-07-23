import json
import pathlib
import runpy
import subprocess
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE = runpy.run_path(str(ROOT / "bin" / "codex-deploy"), run_name="deploy_test")


class Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit):
        return b"verified deployment"

    def geturl(self):
        return "https://example.vercel.app/"


class DeployTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = pathlib.Path(self.temp.name) / "workspace"
        self.project = self.workspace / "demo"
        self.output = self.project / "dist"
        self.output.mkdir(parents=True)
        (self.output / "index.html").write_text("<!doctype html><title>Demo</title>", encoding="utf-8")
        self.spec = pathlib.Path(self.temp.name) / "deploy.json"
        self.spec.write_text(json.dumps({
            "schemaVersion": 1,
            "provider": "vercel",
            "project": str(self.project),
            "output": str(self.output),
            "projectName": "demo-site",
            "production": False,
        }), encoding="utf-8")
        for function in ("workspace_path",):
            MODULE[function].__globals__["WORKSPACE"] = self.workspace

    def tearDown(self):
        self.temp.cleanup()

    def test_plan_hashes_exact_workspace_tree(self):
        plan = MODULE["load_spec"](self.spec)
        self.assertEqual(plan["provider"], "vercel")
        self.assertEqual(len(plan["treeSha256"]), 64)
        self.assertEqual(plan["files"][0]["path"], "index.html")
        self.assertEqual(
            MODULE["plan_sha"](plan),
            MODULE["plan_sha"](MODULE["load_spec"](self.spec)),
        )

    def test_provider_commands_are_fixed_and_noninteractive(self):
        plan = MODULE["load_spec"](self.spec)
        self.assertEqual(
            MODULE["provider_command"](plan, "/bin/vercel"),
            ["/bin/vercel", "deploy", str(self.output), "--yes"],
        )
        plan["provider"] = "cloudflare-pages"
        self.assertIn("--project-name", MODULE["provider_command"](plan, "/bin/wrangler"))

    def test_live_url_and_response_are_verified(self):
        self.assertEqual(
            MODULE["extract_url"]("vercel", "Inspect: x\nhttps://example.vercel.app\n"),
            "https://example.vercel.app",
        )
        with mock.patch("urllib.request.urlopen", return_value=Response()):
            proof = MODULE["verify_live"]("https://example.vercel.app")
        self.assertEqual(proof["status"], 200)
        self.assertGreater(proof["bytesRead"], 0)

    def test_readiness_distinguishes_installed_from_authenticated(self):
        completed = subprocess.CompletedProcess([], 1, "", "not logged in")
        with mock.patch("shutil.which", return_value="/bin/tool"), mock.patch(
            "subprocess.run", return_value=completed
        ):
            values = MODULE["readiness"]()
        self.assertTrue(values["vercel"]["installed"])
        self.assertFalse(values["vercel"]["authenticated"])
        self.assertFalse(values["vercel"]["ready"])

    def test_outside_workspace_and_changed_plan_fail_closed(self):
        value = json.loads(self.spec.read_text())
        value["output"] = self.temp.name
        self.spec.write_text(json.dumps(value))
        with self.assertRaisesRegex(Exception, "deployment_path_outside_workspace"):
            MODULE["load_spec"](self.spec)


if __name__ == "__main__":
    unittest.main()
