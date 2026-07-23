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
MODULE = runpy.run_path(str(ROOT / "bin" / "codex-ui-safe"), run_name="ui_safe_test")
XML_BEFORE = '<hierarchy><node text="Delete" resource-id="app:id/delete" content-desc="" class="android.widget.Button" clickable="true" enabled="true" bounds="[10,20][110,80]" /></hierarchy>'
XML_AFTER = '<hierarchy><node text="Done" resource-id="app:id/done" content-desc="" class="android.widget.TextView" clickable="false" enabled="true" bounds="[10,20][110,80]" /></hierarchy>'


class Result:
    def __init__(self, stdout="", status=0):
        self.stdout = stdout
        self.stderr = ""
        self.remote_status = status
        self.outer_status = 0
        self.combined = stdout


class UiSafeTests(unittest.TestCase):
    def test_selector_validation_matching_and_ambiguity(self):
        root = MODULE["ET"].fromstring(XML_BEFORE)
        wanted = MODULE["selector"]({"resourceId": "app:id/delete", "clickable": True})
        self.assertEqual(MODULE["center"](MODULE["find"](root, wanted)), (60, 50))
        with self.assertRaisesRegex(Exception, "selector_invalid"):
            MODULE["selector"]({"xpath": "//node"})
        duplicate = MODULE["ET"].fromstring(
            '<hierarchy><node text="x" bounds="[0,0][1,1]"/><node text="x" bounds="[1,1][2,2]"/></hierarchy>'
        )
        with self.assertRaisesRegex(Exception, "selector_ambiguous"):
            MODULE["find"](duplicate, {"text": "x"})

    def test_semantic_selector_understands_common_action_equivalents(self):
        root = MODULE["ET"].fromstring(
            '<hierarchy>'
            '<node text="Done" resource-id="app:id/complete" content-desc="" class="android.widget.Button" clickable="true" enabled="true" bounds="[10,20][110,80]" />'
            '<node text="Help" resource-id="app:id/help" content-desc="" class="android.widget.Button" clickable="true" enabled="true" bounds="[10,90][110,150]" />'
            '</hierarchy>'
        )
        target = MODULE["find"](root, MODULE["selector"]({
            "semanticText": "save", "clickable": True, "enabled": True,
        }))
        self.assertEqual(target.attrib["text"], "Done")
        suggestions = MODULE["semantic_suggestions"](root, "save changes", 5)
        self.assertEqual(suggestions[0]["text"], "Done")
        self.assertGreaterEqual(suggestions[0]["score"], 60)

    def test_semantic_selector_refuses_close_competing_targets(self):
        root = MODULE["ET"].fromstring(
            '<hierarchy>'
            '<node text="Continue" clickable="true" enabled="true" bounds="[0,0][10,10]" />'
            '<node text="Next" clickable="true" enabled="true" bounds="[20,0][30,10]" />'
            '</hierarchy>'
        )
        with self.assertRaisesRegex(Exception, "semantic_selector_ambiguous"):
            MODULE["find"](root, {"semanticText": "continue", "clickable": True})

    def test_semantic_suggestions_omit_password_nodes(self):
        root = MODULE["ET"].fromstring(
            '<hierarchy>'
            '<node text="Login" password="true" enabled="true" bounds="[0,0][10,10]" />'
            '<node text="Sign in" password="false" clickable="true" enabled="true" bounds="[20,0][30,10]" />'
            '</hierarchy>'
        )
        suggestions = MODULE["semantic_suggestions"](root, "login", 5)
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]["text"], "Sign in")

    def test_read_only_ui_inspection_retries_missing_remote_status(self):
        missing = MODULE["AndroidBridgeError"]("remote_status_missing")
        completed = Result("<hierarchy/>")
        run = mock.Mock(side_effect=[missing, completed])
        with mock.patch.dict(MODULE["read_rish"].__globals__, {"run_rish": run}), \
             mock.patch.object(MODULE["time"], "sleep"):
            result = MODULE["read_rish"]("uiautomator dump")
        self.assertIs(result, completed)
        self.assertEqual(run.call_count, 2)

    def test_workflow_requires_postconditions_and_rejects_bad_fallback(self):
        with self.assertRaisesRegex(Exception, "selector_invalid"):
            MODULE["validate_spec"]([{"action": "click", "selector": {"text": "x"}}])
        with self.assertRaisesRegex(Exception, "fallback_coordinates_invalid"):
            MODULE["validate_spec"]([{
                "action": "click", "fallbackCoordinates": [-1, 2], "after": {"text": "Done"},
            }])

    def test_click_uses_selector_and_verifies_after_without_real_device(self):
        calls = []
        snapshots = iter((XML_BEFORE, XML_AFTER))

        def fake_rish(command, **_kwargs):
            calls.append(command)
            if command == "dumpsys activity activities":
                return Result("topResumedActivity=ActivityRecord{} u0 com.example/.Main}")
            if command.startswith("uiautomator dump"):
                return Result(next(snapshots))
            if command.startswith("input tap"):
                return Result()
            raise AssertionError(command)

        with tempfile.TemporaryDirectory() as temp:
            spec = pathlib.Path(temp) / "steps.json"
            spec.write_text(json.dumps([{
                "action": "click", "selector": {"resourceId": "app:id/delete"},
                "after": {"resourceId": "app:id/done"}, "retries": 1,
            }]), encoding="utf-8")
            output = io.StringIO()
            with mock.patch.object(sys, "argv", ["codex-ui-safe", "run", "--package", "com.example", "--spec", str(spec)]), \
                 mock.patch.dict(MODULE["main"].__globals__, {"run_rish": fake_rish}), \
                 contextlib.redirect_stdout(output):
                self.assertEqual(MODULE["main"](), 0)
            receipt = json.loads(output.getvalue())
            self.assertTrue(receipt["taskVerified"])
            self.assertTrue(receipt["events"][0]["postconditionVerified"])
            self.assertIn("input tap 60 50", calls)


if __name__ == "__main__":
    unittest.main()
