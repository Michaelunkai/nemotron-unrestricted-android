import hashlib
import io
import json
import pathlib
import runpy
import subprocess
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE = runpy.run_path(str(ROOT / "bin/codex-device-io"), run_name="device_io_test")


class DeviceIOTests(unittest.TestCase):
    def run_main(self, arguments, responses, stdin=""):
        mocked_invoke = mock.Mock(side_effect=responses)
        with (
            mock.patch("sys.argv", ["codex-device-io", *arguments]),
            mock.patch("sys.stdin", io.StringIO(stdin)),
            mock.patch("sys.stdout", new_callable=io.StringIO) as stdout,
            mock.patch("sys.stderr", new_callable=io.StringIO) as stderr,
            mock.patch.dict(MODULE["main"].__globals__, {"invoke": mocked_invoke}),
        ):
            code = MODULE["main"]()
        return code, stdout.getvalue(), stderr.getvalue(), mocked_invoke

    def test_clipboard_set_uses_stdin_redacts_and_verifies_readback(self):
        value = "private value"
        responses = [
            subprocess.CompletedProcess([], 0, "", ""),
            subprocess.CompletedProcess([], 0, value, ""),
        ]
        code, stdout, _, invoked = self.run_main(["clipboard-set"], responses, value)
        self.assertEqual(code, 0)
        receipt = json.loads(stdout)
        self.assertNotIn(value, stdout)
        self.assertEqual(receipt["sha256"], hashlib.sha256(value.encode()).hexdigest())
        self.assertEqual(invoked.call_args_list[0].kwargs["stdin"], value)

    def test_notification_content_is_not_in_argv_or_receipt(self):
        content = "sensitive notification"
        response = subprocess.CompletedProcess([], 0, "", "")
        code, stdout, _, invoked = self.run_main(
            ["notify", "--title", "Automation", "--priority", "high"],
            [response],
            content,
        )
        self.assertEqual(code, 0)
        self.assertNotIn(content, stdout)
        self.assertNotIn(content, invoked.call_args.args[1])
        self.assertEqual(invoked.call_args.kwargs["stdin"], content)

    def test_volume_set_requires_exact_readback(self):
        before = json.dumps([{"stream": "music", "volume": 5, "max_volume": 15}])
        after = json.dumps([{"stream": "music", "volume": 8, "max_volume": 15}])
        responses = [
            subprocess.CompletedProcess([], 0, before, ""),
            subprocess.CompletedProcess([], 0, "", ""),
            subprocess.CompletedProcess([], 0, after, ""),
        ]
        code, stdout, _, _ = self.run_main(
            ["volume", "set", "--stream", "music", "--level", "50"], responses
        )
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(stdout)["taskVerified"])


if __name__ == "__main__":
    unittest.main()
