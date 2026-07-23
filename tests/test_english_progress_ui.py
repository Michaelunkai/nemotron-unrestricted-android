import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "vendor" / "codexapp-native-npm" / "node_modules" / "codexapp" / "dist" / "assets"
MAIN = ASSETS / "index-BjdL8GKN.js"
THREAD = ASSETS / "ThreadConversation-BjC7GMPc.js"
PATCHER = ROOT / "tools" / "patch-codexapp-ui.py"
OVERLAY = ROOT / "web" / "nemotron-autonomy-progress.js"


class EnglishProgressUiTests(unittest.TestCase):
    def test_native_activity_and_group_summaries_are_english_not_raw_commands(self):
        main = MAIN.read_text(encoding="utf-8")
        thread = THREAD.read_text(encoding="utf-8")
        self.assertNotIn('label:"Running command",details:[((El=ws.commandExecution)', main)
        self.assertIn('label:"Working",details:[', main)
        self.assertIn('function Zn(e)', thread)
        self.assertIn('U.humanizeCommand(i)', thread)
        self.assertNotIn('latest: ${i}', thread)

    def test_command_group_summary_is_an_accessible_live_status(self):
        thread = THREAD.read_text(encoding="utf-8")
        self.assertIn('role:"status","aria-live":"polite","aria-atomic":"true"', thread)
        self.assertIn('<code class="hljs"', thread)
        self.assertIn("commandExecution", thread)

    def test_patcher_owns_both_main_and_lazy_chunk_contracts(self):
        patcher = PATCHER.read_text(encoding="utf-8")
        self.assertIn("THREAD_ASSET", patcher)
        self.assertIn("BASE_THREAD_COMMAND_SUMMARY", patcher)
        self.assertIn("PATCHED_THREAD_COMMAND_SUMMARY", patcher)
        self.assertIn("BASE_THREAD_STATUS_SPAN", patcher)
        self.assertIn("PATCHED_THREAD_STATUS_SPAN", patcher)

    def test_no_floating_progress_controls_are_restored(self):
        overlay = OVERLAY.read_text(encoding="utf-8")
        render = overlay[
            overlay.index("function render()"):
            overlay.index("function progressCategory")
        ]
        self.assertIn("removeFloatingUi();", render)
        self.assertNotIn("appendChild", render)


if __name__ == "__main__":
    unittest.main()
