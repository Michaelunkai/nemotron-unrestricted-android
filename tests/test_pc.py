import json
import os
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PC = ROOT / "bin" / "codex-pc"


class PcTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT / "build")
        base = pathlib.Path(self.temporary.name)
        self.record = base / "payload.json"
        self.fake = base / "codex-win"
        self.fake.write_text(
            "#!/data/data/com.termux/files/usr/bin/python\n"
            "import json,os,sys\n"
            "payload=json.loads(sys.argv[1])\n"
            "open(os.environ['PC_RECORD'],'w').write(json.dumps(payload))\n"
            "mode=os.environ.get('PC_MODE','ok')\n"
            "if mode=='policy':\n"
            " print(json.dumps({'error':'command_quote','message':'blocked'}),file=sys.stderr); raise SystemExit(64)\n"
            "stdout=json.dumps({'Name':'expected'}) if mode=='json' else 'readback'\n"
            "print(json.dumps({'ok':True,'verified':True,'exitCode':0,'stdout':stdout,'stderr':''}))\n",
            encoding="utf-8",
        )
        self.fake.chmod(0o700)

    def tearDown(self):
        self.temporary.cleanup()

    def invoke(self, *arguments, mode="ok"):
        return subprocess.run(
            [str(PC), *arguments], cwd=ROOT,
            env={**os.environ, "NEMOTRON_CODEX_WIN": str(self.fake), "PC_RECORD": str(self.record), "PC_MODE": mode},
            capture_output=True, text=True, timeout=10, check=False,
        )

    def test_query_preserves_exact_command_as_one_json_argument(self):
        command = "Get-Item -LiteralPath 'C:\\Program Files\\A B' | Select-Object Name"
        result = self.invoke("query", "--command", command, "--require-output")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.record.read_text())["command"], command)
        self.assertTrue(json.loads(result.stdout)["taskVerified"])

    def test_policy_and_postcondition_failures_are_classified(self):
        policy = self.invoke("query", "--command", "Get-Date", mode="policy")
        self.assertEqual(policy.returncode, 64)
        self.assertEqual(json.loads(policy.stderr)["failureCategory"], "policy")
        mismatch = self.invoke(
            "query", "--command", "Get-Date",
            "--expect-json-field", "Name", "--expect-json-value", "wrong",
            mode="json",
        )
        self.assertEqual(mismatch.returncode, 7)
        self.assertEqual(json.loads(mismatch.stderr)["failureCategory"], "postcondition")


if __name__ == "__main__":
    unittest.main()
