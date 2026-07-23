import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class ReproducibleBuildTests(unittest.TestCase):
    def test_dex_and_signature_entry_clock_source_is_fixed(self):
        source = (ROOT / "build-nemotron-unrestricted.sh").read_text(encoding="utf-8")
        self.assertIn('REPRODUCIBLE_ZIP_DATE="2008-01-01T00:00:00Z"', source)
        self.assertEqual(source.count('--date="$REPRODUCIBLE_ZIP_DATE"'), 3)
        self.assertNotIn('jar uf "$WORK_DIR/unsigned.apk"', source)
        self.assertNotIn('jar uf "$WORK_DIR/unsigned-debug.apk"', source)


if __name__ == "__main__":
    unittest.main()
