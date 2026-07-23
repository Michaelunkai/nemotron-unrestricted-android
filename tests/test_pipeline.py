import json
import os
import pathlib
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
COMMAND = ROOT / "bin" / "codex-pipeline"
SCAFFOLD = ROOT / "bin" / "codex-scaffold"


class PipelineTests(unittest.TestCase):
    def invoke(self, *args):
        result = subprocess.run([str(COMMAND), *args], cwd=ROOT, capture_output=True, text=True, check=False)
        return result, json.loads(result.stdout if result.returncode == 0 else result.stderr)

    def setUp(self):
        name = "pipeline-source-" + os.urandom(3).hex()
        made = subprocess.run([str(SCAFFOLD), "create", "html-static", name], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(made.returncode, 0, made.stderr)
        self.scaffold = json.loads(made.stdout)
        self.project = pathlib.Path(self.scaffold["project"]["target"])
        self.target = ROOT / "workspace" / ("pipeline-target-" + os.urandom(3).hex())
        self.spec = self.project / "pipeline.json"
        self.spec.write_text(json.dumps({
            "schemaVersion": 1, "project": str(self.project),
            "checks": [{"language": "static-web"}],
            "deploy": {"type": "static-copy", "source": ".", "target": str(self.target)},
        }), encoding="utf-8")

    def tearDown(self):
        for path in (self.project, self.target):
            if path.exists():
                subprocess.run(["find", str(path), "-depth", "-delete"], check=False)

    def test_plan_run_verify_and_rollback(self):
        result, plan = self.invoke("plan", str(self.spec))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(plan["dryRun"])
        self.assertFalse(self.target.exists())
        result, run = self.invoke("run", str(self.spec), "--plan-sha256", plan["planSha256"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.target / "index.html").is_file())
        result, rollback = self.invoke("rollback", run["receipt"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.target.exists())

    def test_hash_gate_and_changed_target_fail_closed(self):
        result, failure = self.invoke("run", str(self.spec), "--plan-sha256", "0" * 64)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(failure["error"], "plan_hash_mismatch")
        _, plan = self.invoke("plan", str(self.spec))
        _, run = self.invoke("run", str(self.spec), "--plan-sha256", plan["planSha256"])
        (self.target / "user.txt").write_text("keep", encoding="utf-8")
        result, failure = self.invoke("rollback", run["receipt"])
        self.assertEqual(result.returncode, 2)
        self.assertEqual(failure["error"], "deployment_changed_since_run")
        self.assertTrue((self.target / "user.txt").exists())


if __name__ == "__main__":
    unittest.main()
