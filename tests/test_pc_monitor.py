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


class PcMonitorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT / "build")
        base = pathlib.Path(self.temporary.name)
        self.mode = base / "mode"
        self.mode.write_text("fail")
        self.alerts = base / "alerts"
        pc = base / "pc"
        pc.write_text(
            "#!/bin/sh\n"
            "if [ \"$(cat '" + str(self.mode) + "')\" = ok ]; then\n"
            " echo '{\"verified\":true,\"taskVerified\":true}'\n"
            "else\n"
            " echo '{\"failureCategory\":\"transport\"}' >&2; exit 1\n"
            "fi\n",
            encoding="utf-8",
        )
        pc.chmod(0o700)
        notify = base / "notify"
        notify.write_text("#!/bin/sh\nprintf alert >> '" + str(self.alerts) + "'\n", encoding="utf-8")
        notify.chmod(0o700)
        self.module = runpy.run_path(str(ROOT / "bin/codex-pc-monitor"), run_name="pc_monitor_test")
        globals_ = self.module["main"].__globals__
        globals_["STATE"] = base / "state.json"
        globals_["PID_FILE"] = base / "pid"
        globals_["PC"] = str(pc)
        globals_["NOTIFY"] = str(notify)

    def tearDown(self):
        self.temporary.cleanup()

    def once(self, notify=True):
        output = io.StringIO()
        with mock.patch.object(sys, "argv", ["codex-pc-monitor", "run-once", *(["--notify"] if notify else [])]):
            with contextlib.redirect_stdout(output):
                code = self.module["main"]()
        return code, json.loads(output.getvalue())

    def test_alert_after_three_failures_and_reset_after_verified_success(self):
        for expected in (1, 2, 3):
            code, receipt = self.once()
            self.assertEqual(code, 1)
            self.assertEqual(receipt["state"]["consecutiveFailures"], expected)
        self.assertEqual(self.alerts.read_text(), "alert")
        self.mode.write_text("ok")
        code, receipt = self.once()
        self.assertEqual(code, 0)
        self.assertTrue(receipt["taskVerified"])
        self.assertEqual(receipt["state"]["consecutiveFailures"], 0)


if __name__ == "__main__":
    unittest.main()
