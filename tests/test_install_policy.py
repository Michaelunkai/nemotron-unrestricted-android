import pathlib
import runpy
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class InstallPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = runpy.run_path(str(ROOT / "bin" / "codex-install"), run_name="codex_install_policy_test")

    def test_upgrade_and_equal_version_are_allowed(self):
        enforce = self.module["enforce_version_transition"]
        enforce({"installed": False}, {"versionCode": 1})
        enforce({"installed": True, "versionCode": 2}, {"versionCode": 2})
        enforce({"installed": True, "versionCode": 2}, {"versionCode": 3})

    def test_downgrade_and_unknown_versions_fail_closed(self):
        enforce = self.module["enforce_version_transition"]
        with self.assertRaisesRegex(Exception, "apk_downgrade_blocked"):
            enforce({"installed": True, "versionCode": 3}, {"versionCode": 2})
        with self.assertRaisesRegex(Exception, "version_transition_unverified"):
            enforce({"installed": True, "versionCode": None}, {"versionCode": 2})


if __name__ == "__main__":
    unittest.main()
