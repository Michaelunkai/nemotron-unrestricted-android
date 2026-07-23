import contextlib
import io
import json
import pathlib
import runpy
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT / "build")
        base = pathlib.Path(self.temporary.name)
        self.log = base / "scheduler.log"
        fake = base / "termux-job-scheduler"
        fake.write_text(
            "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"" + str(self.log) + "\"\n"
            "if [ \"$1\" = \"--pending\" ]; then echo '[]'; fi\n",
            encoding="utf-8",
        )
        fake.chmod(0o700)
        self.task = base / "task.json"
        output = base / "result"
        self.task.write_text(json.dumps({
            "schemaVersion": 1, "id": "scheduled-proof", "title": "Scheduled proof",
            "steps": [{
                "id": "touch", "purpose": "Create one verified scheduled result",
                "program": "/data/data/com.termux/files/usr/bin/touch",
                "args": [str(output)], "mutation": True,
                "verify": {"type": "file", "path": str(output)},
            }],
        }), encoding="utf-8")
        self.output = output
        self.module = runpy.run_path(str(ROOT / "bin/codex-schedule"), run_name="codex_schedule_test")
        globals_ = self.module["main"].__globals__
        globals_["STATE"] = base / "state"
        globals_["JOBS"] = base / "state" / "jobs"
        globals_["REGISTRY"] = base / "state" / "registry.json"
        globals_["JOB_SCHEDULER"] = str(fake)

    def tearDown(self):
        task_state = ROOT / "runtime" / ".codex" / "automation" / "tasks"
        for path in task_state.glob("scheduled-proof-proof-*.json"):
            if path.is_file() and not path.is_symlink() and path.parent == task_state:
                path.unlink()
        self.temporary.cleanup()

    def invoke(self, *arguments):
        output = io.StringIO()
        error = io.StringIO()
        with mock.patch.object(sys, "argv", ["codex-schedule", *arguments]):
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
                code = self.module["main"]()
        return code, output.getvalue(), error.getvalue()

    def test_create_pause_resume_cancel_uses_exact_job(self):
        code, output, _ = self.invoke(
            "create", "nightly", "--task", str(self.task),
            "--every-seconds", "900", "--network", "unmetered",
            "--charging", "--persisted",
        )
        self.assertEqual(code, 0)
        row = json.loads(output)["schedule"]
        self.assertEqual(row["network"], "unmetered")
        self.assertTrue(row["charging"])
        self.assertTrue(row["persisted"])
        job_id = str(row["jobId"])
        self.assertIn("--period-ms 900000", self.log.read_text())
        self.assertEqual(self.invoke("pause", "nightly")[0], 0)
        self.assertEqual(self.invoke("resume", "nightly")[0], 0)
        self.assertEqual(self.invoke("cancel", "nightly")[0], 0)
        self.assertGreaterEqual(self.log.read_text().count(f"--cancel {job_id}"), 2)

    def test_run_now_executes_verified_task_and_advances_next_run(self):
        self.assertEqual(self.invoke(
            "create", "proof", "--task", str(self.task), "--every-seconds", "900",
        )[0], 0)
        code, output, error = self.invoke("run-now", "proof")
        self.assertEqual(code, 0, output + error)
        self.assertTrue(self.output.exists())
        events = [json.loads(line) for line in output.splitlines()]
        self.assertEqual(events[-1]["event"], "task-completed")
        code, status, _ = self.invoke("status", "proof")
        self.assertEqual(code, 0)
        row = json.loads(status)["schedule"]
        self.assertEqual(row["lastOutcome"], "verified")
        self.assertGreater(row["nextRunEpoch"], row["lastRunEpoch"])


if __name__ == "__main__":
    unittest.main()
