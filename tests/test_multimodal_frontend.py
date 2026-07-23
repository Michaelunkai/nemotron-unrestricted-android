import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "vendor" / "codexapp-native-npm" / "node_modules" / "codexapp" / "dist" / "assets"


class MultimodalFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scripts = "\n".join(path.read_text(encoding="utf-8") for path in ASSETS.glob("*.js"))

    def test_local_and_remote_images_are_attached_to_turn_input(self):
        self.assertIn('type:"localImage",path:', self.scripts)
        self.assertIn('type:"image",url:', self.scripts)
        self.assertIn('image_url:', self.scripts)

    def test_completed_image_items_are_rendered_in_the_same_conversation(self):
        self.assertIn('i.method!=="item/completed"', self.scripts)
        self.assertIn('g.type==="imageView"', self.scripts)
        self.assertIn('g.type!=="imageGeneration"&&g.type!=="image_generation"', self.scripts)
        self.assertIn('messageType:"imageView"', self.scripts)

    def test_generated_images_have_clickable_visible_preview(self):
        self.assertIn('class:"message-image-button"', self.scripts)
        self.assertIn('alt:t.messageType==="imageView"?"Generated image":"Message image preview"', self.scripts)
        self.assertIn('message-generated-image-preview', self.scripts)

    def test_verified_gallery_results_render_without_model_markdown(self):
        self.assertIn("function nemotronGalleryResult", self.scripts)
        self.assertIn("nemotron.gallery-result.v1", self.scripts)
        self.assertIn("verified-local-image-grid", self.scripts)
        self.assertIn("nemotron-gallery-image-list", self.scripts)
        self.assertIn("nemotronGalleryResult(e)!==null", self.scripts)


if __name__ == "__main__":
    unittest.main()
