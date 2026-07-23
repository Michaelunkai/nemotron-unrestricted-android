import io
import json
import pathlib
import runpy
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))
MODULE = runpy.run_path(str(ROOT / "bin/codex-care"), run_name="care_test")


class CareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "build")
        self.base = pathlib.Path(self.temp.name)
        self.runtime = self.base / "runtime" / ".codex"
        self.backups = self.base / "backups"
        self.state = self.base / "state"
        self.restore_root = self.base / "restore"
        self.runtime.mkdir(parents=True)
        (self.runtime / "config.toml").write_text("setting = true\n", encoding="utf-8")
        self.globals = {
            "RUNTIME": self.runtime,
            "STATE": self.state,
            "BACKUP_ROOT": self.backups,
            "INCLUDE": (self.runtime / "config.toml",),
            "RESTORE_ROOTS": (self.restore_root,),
        }

    def tearDown(self):
        self.temp.cleanup()

    def invoke(self, arguments, passphrase="correct horse battery"):
        stdin = io.TextIOWrapper(io.BytesIO((passphrase + "\n").encode()))
        try:
            with (
                mock.patch("sys.argv", ["codex-care", *arguments]),
                mock.patch("sys.stdin", stdin),
                mock.patch("sys.stdout", new_callable=io.StringIO) as stdout,
                mock.patch("sys.stderr", new_callable=io.StringIO) as stderr,
                mock.patch.dict(MODULE["main"].__globals__, self.globals),
            ):
                code = MODULE["main"]()
            return code, stdout.getvalue(), stderr.getvalue()
        finally:
            stdin.close()

    def test_backup_verify_and_isolated_restore(self):
        code, stdout, _ = self.invoke(["backup", "proof.nmbak"])
        self.assertEqual(code, 0)
        backup = pathlib.Path(json.loads(stdout)["backup"])
        self.assertNotIn(b"setting = true", backup.read_bytes())
        code, stdout, _ = self.invoke(["verify", str(backup)])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(stdout)["taskVerified"])
        destination = self.restore_root / "recovered"
        code, stdout, _ = self.invoke(["restore", str(backup), str(destination)])
        self.assertEqual(code, 0)
        self.assertEqual(
            (destination / self.runtime.relative_to(ROOT) / "config.toml").read_text(encoding="utf-8"),
            "setting = true\n",
        )

    def test_wrong_passphrase_fails_authentication(self):
        code, stdout, _ = self.invoke(["backup", "proof.nmbak"])
        self.assertEqual(code, 0)
        backup = json.loads(stdout)["backup"]
        code, stdout, stderr = self.invoke(["recovery-drill", backup], "this is the wrong passphrase")
        self.assertEqual(code, 2)
        self.assertTrue(stderr, f"authentication failure emitted no stderr JSON; stdout={stdout!r}")
        receipts = [line for line in stderr.splitlines() if line.lstrip().startswith("{")]
        self.assertTrue(receipts, f"authentication failure emitted no JSON receipt: {stderr!r}")
        self.assertEqual(json.loads(receipts[-1])["error"], "backup_authentication_failed")

    def test_upkeep_is_hash_bound_and_backs_up_database(self):
        automation = self.runtime / "automation"
        automation.mkdir()
        database = automation / "state.db"
        with sqlite3.connect(database) as connection:
            connection.execute(
                "CREATE TABLE cache(namespace TEXT,key TEXT,value_json TEXT,created_at INTEGER,expires_at INTEGER)"
            )
            connection.execute("INSERT INTO cache VALUES('test','old','{}',1,1)")
        plan = self.base / "upkeep.json"
        code, stdout, _ = self.invoke(
            ["upkeep-plan", "--output", str(plan), "--log-days", "7"]
        )
        self.assertEqual(code, 0)
        receipt = json.loads(stdout)
        self.assertEqual(receipt["expiredCacheEntries"], 1)
        code, stdout, _ = self.invoke(
            ["upkeep-apply", "--plan", str(plan), "--sha256", receipt["planSha256"]]
        )
        self.assertEqual(code, 0)
        result = json.loads(stdout)
        self.assertTrue(pathlib.Path(result["databaseBackup"]).is_file())
        with sqlite3.connect(database) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM cache").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
