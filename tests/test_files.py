import json
import pathlib
import subprocess
import tempfile
import unittest
import zipfile


ROOT = pathlib.Path(__file__).resolve().parents[1]
FILES = ROOT / "bin/codex-files"


class FilesTests(unittest.TestCase):
    def invoke(self, *args):
        return subprocess.run([str(FILES), *args], cwd=ROOT, capture_output=True, text=True, check=False)

    def test_copy_and_archive_round_trip_are_checksum_verified(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "workspace") as temporary:
            base = pathlib.Path(temporary)
            source = base / "source.txt"
            source.write_text("verified bytes\n", encoding="utf-8")
            copied = base / "copied.txt"
            result = self.invoke("copy", str(source), str(copied))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout)["taskVerified"])
            archive = base / "proof.zip"
            result = self.invoke("archive-create", str(archive), str(source), str(copied))
            self.assertEqual(result.returncode, 0, result.stderr)
            listed = self.invoke("archive-list", str(archive))
            self.assertEqual(listed.returncode, 0, listed.stderr)
            destination = base / "extracted"
            extracted = self.invoke("archive-extract", str(archive), str(destination))
            self.assertEqual(extracted.returncode, 0, extracted.stderr)
            self.assertEqual((destination / "source.txt").read_bytes(), source.read_bytes())

    def test_archive_traversal_and_overwrite_are_refused(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "workspace") as temporary:
            base = pathlib.Path(temporary)
            archive = base / "bad.zip"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("../escape", "blocked")
            result = self.invoke("archive-extract", str(archive), str(base / "destination"))
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stderr)["error"], "archive_traversal_refused")
            source = base / "source"
            destination = base / "destination"
            source.write_text("new", encoding="utf-8")
            destination.write_text("old", encoding="utf-8")
            result = self.invoke("copy", str(source), str(destination))
            self.assertEqual(result.returncode, 2)
            self.assertEqual(destination.read_text(encoding="utf-8"), "old")

    def test_paths_outside_managed_roots_are_refused(self):
        result = self.invoke("inspect", "/system/build.prop")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stderr)["error"], "path_outside_managed_roots")


if __name__ == "__main__":
    unittest.main()
