import pathlib
import runpy
import sys
import tempfile
import unittest
import zipfile


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))
MODULE = runpy.run_path(str(ROOT / "bin/codex-security"), run_name="security_test")


class SecurityTests(unittest.TestCase):
    def test_policy_probes_are_all_blocked(self):
        receipt = MODULE["policy_checks"]()
        self.assertTrue(receipt["verified"])
        self.assertEqual(len(receipt["blockedProbes"]), 4)

    def test_safe_archive_is_hashed_without_extraction(self):
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "safe.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("folder/file.txt", "safe")
            receipt = MODULE["artifact"](str(path))
            self.assertTrue(receipt["taskVerified"])
            self.assertEqual(receipt["archiveMemberCount"], 1)
            self.assertEqual(len(receipt["sha256"]), 64)
            self.assertFalse((path.parent / "folder").exists())

    def test_path_traversal_and_symlink_archive_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "bad.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("../escape", "bad")
            with self.assertRaisesRegex(Exception, "archive_unsafe_member"):
                MODULE["artifact"](str(path))
            link = pathlib.Path(temp) / "link"
            link.symlink_to(path)
            with self.assertRaisesRegex(Exception, "artifact_invalid"):
                MODULE["artifact"](str(link))


if __name__ == "__main__":
    unittest.main()
