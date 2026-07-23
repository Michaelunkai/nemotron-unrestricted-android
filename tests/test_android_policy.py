import pathlib
import tempfile
import unittest
from unittest import mock

from PIL import Image


ROOT = pathlib.Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "bin"))
import nemotron_android_policy as POLICY


class AndroidPolicyReadbackTests(unittest.TestCase):
    def test_staged_readback_requires_matching_remote_and_local_bytes(self):
        payload = b"complete remote output\nsecond line\n"
        with tempfile.TemporaryDirectory() as temporary:
            stage = pathlib.Path(temporary)

            def fake_run(command, **_kwargs):
                target = next(
                    pathlib.Path(token)
                    for token in command.split()
                    if token.startswith(str(stage / "readback-"))
                )
                target.write_bytes(payload)
                digest = POLICY.hashlib.sha256(payload).hexdigest()
                return POLICY.RemoteResult(
                    f"NEMOTRON_READBACK bytes={len(payload)} sha256={digest}\n",
                    "", 0, 0,
                )

            with mock.patch.object(POLICY, "STAGED_READ_ROOT", stage), \
                 mock.patch.object(POLICY, "run_rish", side_effect=fake_run):
                result = POLICY.read_rish_staged("dumpsys package com.example")
            self.assertEqual(result.text, payload.decode())
            self.assertEqual(result.bytes, len(payload))
            self.assertFalse(any(stage.iterdir()))

    def test_staged_readback_rejects_hash_mismatch_and_cleans_up(self):
        payload = b"tampered"
        with tempfile.TemporaryDirectory() as temporary:
            stage = pathlib.Path(temporary)

            def fake_run(command, **_kwargs):
                target = next(
                    pathlib.Path(token)
                    for token in command.split()
                    if token.startswith(str(stage / "readback-"))
                )
                target.write_bytes(payload)
                return POLICY.RemoteResult(
                    f"NEMOTRON_READBACK bytes={len(payload)} sha256={'0' * 64}\n",
                    "", 0, 0,
                )

            with mock.patch.object(POLICY, "STAGED_READ_ROOT", stage), \
                 mock.patch.object(POLICY, "run_rish", side_effect=fake_run):
                with self.assertRaisesRegex(Exception, "staged_readback_integrity_failed"):
                    POLICY.read_rish_staged("dumpsys package com.example")
            self.assertFalse(any(stage.iterdir()))

    def test_png_verification_decodes_dimensions_and_hashes_actual_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = pathlib.Path(temporary) / "proof.png"
            Image.new("RGB", (31, 17), (20, 120, 220)).save(path, format="PNG")
            receipt = POLICY.verify_png_file(path)
            self.assertTrue(receipt["verified"])
            self.assertEqual((receipt["width"], receipt["height"]), (31, 17))
            self.assertEqual(receipt["format"], "PNG")
            self.assertEqual(receipt["sha256"], POLICY.hashlib.sha256(path.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
