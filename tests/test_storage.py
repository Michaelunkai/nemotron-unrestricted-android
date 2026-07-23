import json
import os
import pathlib
import runpy
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT / "build")
        base = pathlib.Path(self.temporary.name)
        self.termux = base / "termux"
        self.runtime = base / "runtime"
        self.targets = {}
        for name in ("shared", "downloads", "pictures", "dcim", "movies", "music"):
            target = base / "android" / name
            target.mkdir(parents=True)
            self.targets[name] = target
        self.module = runpy.run_path(str(ROOT / "bin/codex-storage"), run_name="codex_storage_test")
        globals_ = self.module["main"].__globals__
        globals_["TERMUX_HOME"] = self.termux
        globals_["RUNTIME_HOME"] = self.runtime
        globals_["TARGETS"] = self.targets

    def tearDown(self):
        self.temporary.cleanup()

    def invoke(self, command):
        output = []
        with mock.patch.object(sys, "argv", ["codex-storage", command]):
            with mock.patch("builtins.print", side_effect=lambda value, **_kwargs: output.append(value)):
                code = self.module["main"]()
        return code, json.loads(output[-1])

    def test_enable_and_disable_exact_links_without_touching_targets(self):
        code, enabled = self.invoke("enable")
        self.assertEqual(code, 0)
        self.assertTrue(enabled["taskVerified"])
        self.assertEqual(enabled["changed"], 12)
        code, disabled = self.invoke("disable")
        self.assertEqual(code, 0)
        self.assertTrue(disabled["taskVerified"])
        self.assertTrue(all(target.exists() for target in self.targets.values()))

    def test_existing_path_is_refused(self):
        path = self.termux / "storage" / "shared"
        path.mkdir(parents=True)
        (path / "user-file").write_text("keep", encoding="utf-8")
        code, error = self.invoke("enable")
        self.assertEqual(code, 2)
        self.assertIn("existing_path_refused", error["error"])
        self.assertTrue((path / "user-file").exists())


if __name__ == "__main__":
    unittest.main()
