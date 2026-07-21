import importlib.util
from importlib.machinery import SourceFileLoader
import pathlib
import sys
import types
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))
SOURCE = ROOT / "bin" / "codex-gallery"
SPEC = importlib.util.spec_from_loader("codex_gallery", SourceFileLoader("codex_gallery", str(SOURCE)))
GALLERY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GALLERY)


class GalleryTests(unittest.TestCase):
    def test_rows_are_parsed_into_typed_media_records(self):
        rows = GALLERY.parse_rows(
            "Row: 0 _id=42, _display_name=Screenshot_demo.jpg, relative_path=DCIM/Screenshots/, "
            "date_added=1784643209, date_modified=1784643209, mime_type=image/jpeg, _size=70445\n",
            "image",
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["_id"], 42)
        self.assertEqual(rows[0]["_size"], 70445)
        self.assertEqual(rows[0]["relative_path"], "DCIM/Screenshots/")

    def test_delete_trashes_exact_item_and_returns_restore_contract(self):
        args = types.SimpleNamespace(action="delete", kind="image", id=42, confirm="DELETE_MEDIA_ID_42")
        before = {"_id": 42, "_display_name": "fixture.jpg", "mime_type": "image/jpeg", "is_trashed": 0}
        trashed = {**before, "is_trashed": 1}
        with mock.patch.object(GALLERY, "exact_record", side_effect=[before, None, trashed]), \
             mock.patch.object(GALLERY, "run_rish", return_value=types.SimpleNamespace(remote_status=0)) as run, \
             mock.patch.object(GALLERY, "write_audit") as audit:
            result, status = GALLERY.exact_action(args)
        self.assertEqual(status, 0)
        self.assertTrue(result["verifiedRecoverable"])
        self.assertEqual(result["restoreConfirmation"], "RESTORE_MEDIA_ID_42")
        self.assertIn("content update", run.call_args.args[0])
        self.assertIn("is_trashed:i:1", run.call_args.args[0])
        audit.assert_called_once_with("trash", before, trashed)

    def test_restore_untrashes_exact_item_and_verifies_presence(self):
        args = types.SimpleNamespace(action="restore", kind="image", id=42, confirm="RESTORE_MEDIA_ID_42")
        trashed = {"_id": 42, "_display_name": "fixture.jpg", "mime_type": "image/jpeg", "is_trashed": 1}
        restored = {**trashed, "is_trashed": 0}
        with mock.patch.object(GALLERY, "exact_record", side_effect=[trashed, restored]), \
             mock.patch.object(GALLERY, "run_rish", return_value=types.SimpleNamespace(remote_status=0)) as run, \
             mock.patch.object(GALLERY, "write_audit") as audit:
            result, status = GALLERY.exact_action(args)
        self.assertEqual(status, 0)
        self.assertTrue(result["verifiedPresent"])
        self.assertIn("is_trashed:i:0", run.call_args.args[0])
        audit.assert_called_once_with("restore", trashed, restored)

    def test_safe_media_path_rejects_traversal_and_accepts_gallery_record(self):
        self.assertEqual(
            GALLERY.safe_media_path({"relative_path": "DCIM/Screenshots/", "_display_name": "shot.jpg"}),
            "/storage/emulated/0/DCIM/Screenshots/shot.jpg",
        )
        self.assertIsNone(GALLERY.safe_media_path({"relative_path": "../private/", "_display_name": "shot.jpg"}))
        self.assertIsNone(GALLERY.safe_media_path({"relative_path": "DCIM/", "_display_name": "../shot.jpg"}))

    def test_face_inventory_reports_only_local_face_presence(self):
        now = 1_800_000_000
        record = {
            "_id": 42, "_display_name": "people.jpg", "relative_path": "DCIM/Camera/",
            "date_added": now - 10, "mime_type": "image/jpeg", "is_trashed": 0,
        }
        build = types.SimpleNamespace(returncode=0, stdout="/tmp/detector.jar\n", stderr="")
        detection = types.SimpleNamespace(
            remote_status=0,
            stdout='{"path":"/storage/emulated/0/DCIM/Camera/people.jpg","faceCount":2}\n',
            stderr="",
        )
        staged = types.SimpleNamespace(remote_status=0, stdout="", stderr="")
        remote_hash = types.SimpleNamespace(remote_status=0, stdout="PLACEHOLDER", stderr="")
        args = types.SimpleNamespace(hours=24, limit=10, min_faces=1)
        with mock.patch.object(GALLERY, "query_kind", return_value=[record]), \
             mock.patch.object(GALLERY.time, "time", return_value=now), \
             mock.patch.object(GALLERY.subprocess, "run", return_value=build), \
             mock.patch.object(GALLERY.pathlib.Path, "read_bytes", return_value=b"detector"), \
             mock.patch.object(GALLERY.hashlib, "sha256", return_value=types.SimpleNamespace(hexdigest=lambda: "placeholder")), \
             mock.patch.object(GALLERY.shutil, "copyfile"), \
             mock.patch.object(GALLERY.pathlib.Path, "chmod"), \
             mock.patch.object(GALLERY, "run_rish", side_effect=[staged, remote_hash, detection]):
            result = GALLERY.face_inventory(args)
        self.assertTrue(result["verified"])
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["items"][0]["faceCount"], 2)
        self.assertEqual(result["scope"], "face-presence-only-no-identity-or-gender-inference")

    def test_semantic_search_returns_verified_visible_content_matches(self):
        now = 1_800_000_000
        record = {
            "_id": 7, "_display_name": "dog.jpg", "relative_path": "DCIM/Camera/",
            "date_added": now - 10, "mime_type": "image/jpeg", "is_trashed": 0,
        }
        args = types.SimpleNamespace(query="a dog near a red ball", hours=24, limit=10)
        with mock.patch.object(GALLERY, "query_kind", return_value=[record]), \
             mock.patch.object(GALLERY.time, "time", return_value=now), \
             mock.patch.object(GALLERY, "configured_proxy_port", return_value=18776), \
             mock.patch.object(GALLERY, "vision_match", return_value={"match": True, "description": "A dog beside a red ball.", "reason": "Both requested objects are visible."}):
            result = GALLERY.semantic_inventory(args)
        self.assertTrue(result["verified"])
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["items"][0]["_id"], 7)

    def test_semantic_search_rejects_sensitive_attribute_inference(self):
        args = types.SimpleNamespace(query="find all women", hours=24, limit=10)
        with self.assertRaises(GALLERY.AndroidPolicyError):
            GALLERY.semantic_inventory(args)

    def test_json_only_vision_result_parser_is_bounded_to_an_object(self):
        self.assertEqual(GALLERY.parse_json_object('```json\n{"match":true}\n```'), {"match": True})
        self.assertIsNone(GALLERY.parse_json_object("not json"))

    def test_recent_screenshot_filter_is_bounded_and_human_readable(self):
        args = types.SimpleNamespace(action="recent", kind="image", limit=5, hours=24, screenshots=True)
        now = 1_800_000_000
        fixtures = [
            {"_id": 5, "_display_name": "Screenshot_new.jpg", "relative_path": "DCIM/Screenshots/", "date_added": now - 10, "_size": 100},
            {"_id": 4, "_display_name": "photo.jpg", "relative_path": "DCIM/Camera/", "date_added": now - 10, "_size": 100},
            {"_id": 3, "_display_name": "Screenshot_old.jpg", "relative_path": "DCIM/Screenshots/", "date_added": now - 90000, "_size": 100},
        ]
        with mock.patch.object(GALLERY, "query_kind", return_value=fixtures), mock.patch.object(GALLERY.time, "time", return_value=now):
            result = GALLERY.inventory(args)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["items"][0]["_id"], 5)
        self.assertTrue(result["verified"])

    def test_delete_requires_exact_id_bound_confirmation_before_mutation(self):
        args = types.SimpleNamespace(action="delete", kind="image", id=42, confirm="DELETE")
        record = {"_id": 42, "_display_name": "fixture.jpg", "mime_type": "image/jpeg"}
        with mock.patch.object(GALLERY, "exact_record", return_value=record), mock.patch.object(GALLERY, "run_rish") as run:
            with self.assertRaises(GALLERY.AndroidPolicyError):
                GALLERY.exact_action(args)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
