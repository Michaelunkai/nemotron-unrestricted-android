import json
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
TASK = ROOT / "bin" / "codex-task"


class TaskTests(unittest.TestCase):
    def task_file(self, directory, *, consent=False):
        output = pathlib.Path(directory) / "result.txt"
        task = pathlib.Path(directory) / "task.yaml"
        task.write_text(
            "schemaVersion: 1\n"
            "id: verified-example\n"
            "title: Verified example\n"
            "steps:\n"
            "  - id: create-result\n"
            "    purpose: Create and verify one isolated result\n"
            "    program: /data/data/com.termux/files/usr/bin/touch\n"
            f"    args: [{output}]\n"
            "    mutation: true\n"
            f"    requiresConsent: {'true' if consent else 'false'}\n"
            "    verify:\n"
            "      type: file\n"
            f"      path: {output}\n",
            encoding="utf-8",
        )
        return task, output

    def run_task_command(self, *args):
        return subprocess.run([str(TASK), *args], cwd=ROOT, capture_output=True, text=True, timeout=15, check=False)

    def test_validate_and_dry_run_have_no_side_effect(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "build") as directory:
            task, output = self.task_file(directory)
            self.assertEqual(self.run_task_command("validate", str(task)).returncode, 0)
            dry = self.run_task_command("dry-run", str(task))
            self.assertEqual(dry.returncode, 0)
            self.assertFalse(output.exists())
            self.assertTrue(json.loads(dry.stdout)["taskVerified"])

    def test_run_requires_postcondition_and_checkpoints(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "build") as directory:
            task, output = self.task_file(directory)
            state = ROOT / "runtime" / ".codex" / "automation" / "tasks" / "verified-example.json"
            if state.exists():
                state.unlink()
            result = self.run_task_command("run", str(task))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(output.exists())
            events = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertEqual(events[-1]["event"], "task-completed")
            self.assertTrue(events[-1]["taskVerified"])
            self.assertEqual(json.loads(state.read_text())["status"], "completed")
            state.unlink()

    def test_consent_gate_stops_before_mutation(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "build") as directory:
            task, output = self.task_file(directory, consent=True)
            state = ROOT / "runtime" / ".codex" / "automation" / "tasks" / "verified-example.json"
            if state.exists():
                state.unlink()
            result = self.run_task_command("run", str(task))
            self.assertEqual(result.returncode, 2)
            self.assertFalse(output.exists())
            self.assertIn("consent_required:create-result", result.stdout)
            if state.exists():
                state.unlink()

    def test_retry_without_safe_flag_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "build") as directory:
            task, _ = self.task_file(directory)
            text = task.read_text()
            text = text.replace("    verify:\n", "    retry:\n      attempts: 2\n      safe: false\n    verify:\n")
            task.write_text(text)
            result = self.run_task_command("validate", str(task))
            self.assertEqual(result.returncode, 2)
            self.assertIn("step_retry_safety_required", result.stdout)


if __name__ == "__main__":
    unittest.main()
