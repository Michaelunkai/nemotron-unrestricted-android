import contextlib
import io
import json
import pathlib
import runpy
import subprocess
import sys
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))


class IntentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.android = runpy.run_path(str(ROOT / "bin" / "codex-android"), run_name="android_intent_test")
        cls.intent = runpy.run_path(str(ROOT / "bin" / "codex-intent"), run_name="typed_intent_test")

    def test_uri_extra_is_typed_and_file_uri_rejected(self):
        spec = self.android["intent_spec"](json.dumps({
            "kind": "activity", "action": "android.media.action.IMAGE_CAPTURE",
            "extras": {"output": {"type": "uri", "value": "content://example/output/1"}},
        }))
        self.assertIn("--eu", spec["arguments"])
        with self.assertRaisesRegex(Exception, "intent_extra_uri"):
            self.android["intent_spec"](json.dumps({
                "kind": "activity", "action": "android.media.action.IMAGE_CAPTURE",
                "extras": {"output": {"type": "uri", "value": "file:///tmp/x"}},
            }))

    def invoke(self, *args):
        completed = subprocess.CompletedProcess([], 0, json.dumps({
            "verified": True, "component": "example/.Main", "package": "example",
        }), "")
        output = io.StringIO()
        with mock.patch.object(sys, "argv", ["codex-intent", *args]), \
             mock.patch("subprocess.run", return_value=completed) as called, \
             contextlib.redirect_stdout(output):
            code = self.intent["main"]()
        return code, json.loads(output.getvalue()), called.call_args.args[0]

    def test_high_level_workflows_resolve_without_execute_by_default(self):
        cases = (
            ("open-url", "https://example.com"),
            ("open-app", "com.example.app"),
            ("settings", "com.example.app"),
            ("share-text", "private words"),
            ("view", "content://example/item/1", "--mime", "image/jpeg"),
            ("capture-image", "--output", "content://example/output/1"),
        )
        for case in cases:
            code, receipt, command = self.invoke(*case)
            self.assertEqual(code, 0)
            self.assertTrue(receipt["taskVerified"])
            self.assertFalse(receipt["executed"])
            self.assertEqual(command[1], "resolve-intent")
        _, share, _ = self.invoke("share-text", "private words")
        self.assertNotIn("private words", json.dumps(share["spec"]))

    def test_execute_is_explicit_and_credentialed_url_rejected(self):
        code, receipt, command = self.invoke("open-url", "https://example.com", "--execute")
        self.assertEqual(code, 0)
        self.assertTrue(receipt["executed"])
        self.assertEqual(command[1], "intent")
        with self.assertRaisesRegex(Exception, "uri_invalid"):
            self.intent["build"](type("Args", (), {
                "workflow": "open-url", "url": "https://u:p@example.com", "package": None,
            })())


if __name__ == "__main__":
    unittest.main()
