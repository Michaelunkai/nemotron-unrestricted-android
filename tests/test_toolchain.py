import json
import os
import pathlib
import shutil
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
COMMAND = ROOT / "bin" / "codex-toolchain"
SCAFFOLD = ROOT / "bin" / "codex-scaffold"


class ToolchainTests(unittest.TestCase):
    def invoke(self, *args):
        result = subprocess.run([str(COMMAND), *args], cwd=ROOT, capture_output=True, text=True, check=False)
        return result, json.loads(result.stdout if result.returncode == 0 else result.stderr)

    def scaffold(self, template):
        name = "toolchain-" + template.replace("-app", "").replace("-tool", "") + "-" + os.urandom(3).hex()
        result = subprocess.run([str(SCAFFOLD), "create", template, name], cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_detect_and_verify_python_node_shell_web_java(self):
        for template, language in (
            ("python-app", "python"), ("node-app", "node"), ("shell-tool", "shell"),
            ("html-static", "static-web"), ("java-app", "java"),
        ):
            receipt = self.scaffold(template)
            target = receipt["project"]["target"]
            try:
                result, inspected = self.invoke("inspect", target)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(language, inspected["detected"])
                self.assertTrue(inspected["tools"][language]["adapterAvailable"])
                result, verified = self.invoke("verify", target, "--language", language)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(verified["taskVerified"])
                self.assertTrue(verified["evidence"]["files"])
            finally:
                subprocess.run(["find", target, "-depth", "-delete"], check=False)

    def test_invalid_python_powershell_and_missing_kotlin_fail_closed(self):
        base = ROOT / "workspace" / ("toolchain-invalid-" + os.urandom(3).hex())
        base.mkdir()
        try:
            (base / "bad.py").write_text("if :\n", encoding="utf-8")
            self.assertEqual(self.invoke("verify", str(base), "--language", "python")[0].returncode, 2)
            (base / "bad.py").unlink()
            (base / "bad.ps1").write_text("Write-Output ( 'x'\n", encoding="utf-8")
            self.assertEqual(self.invoke("verify", str(base), "--language", "powershell")[0].returncode, 2)
            (base / "bad.ps1").unlink()
            (base / "Main.kt").write_text("fun main() = println(\"ok\")\n", encoding="utf-8")
            result, receipt = self.invoke("verify", str(base), "--language", "kotlin")
            if shutil.which("kotlinc") is None:
                self.assertEqual(result.returncode, 2)
                self.assertEqual(receipt["error"], "tool_unavailable:kotlinc")
        finally:
            subprocess.run(["find", str(base), "-depth", "-delete"], check=False)

    def test_android_and_powershell_static_adapters(self):
        base = ROOT / "workspace" / ("toolchain-platform-" + os.urandom(3).hex())
        base.mkdir()
        try:
            (base / "AndroidManifest.xml").write_text(
                '<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="example.proof"><application /></manifest>\n',
                encoding="utf-8",
            )
            result, receipt = self.invoke("verify", str(base), "--language", "android")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(receipt["evidence"]["verificationLevel"], "manifest-and-wrapper-static")
            (base / "tool.ps1").write_text(
                "Set-StrictMode -Version Latest\nWrite-Output ('ready')\n", encoding="utf-8",
            )
            result, receipt = self.invoke("verify", str(base), "--language", "powershell")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(receipt["evidence"]["verificationLevel"], "bounded-structural-static")
        finally:
            subprocess.run(["find", str(base), "-depth", "-delete"], check=False)


if __name__ == "__main__":
    unittest.main()
