import hashlib
import pathlib
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "web" / "nemotron-autonomy-progress.js"
DEPLOYED_PATH = (
    ROOT
    / "vendor"
    / "codexapp-native-npm"
    / "node_modules"
    / "codexapp"
    / "dist"
    / "nemotron-autonomy-progress.js"
)
INDEX_PATH = DEPLOYED_PATH.with_name("index.html")


class ProgressOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE_PATH.read_text(encoding="utf-8")

    def test_versioned_epoch_persistence_is_hydrated_before_transport_hooks(self):
        self.assertIn("const VERSION = '4.3.0'", self.source)
        self.assertIn("const STORAGE_PREFIX", self.source)
        self.assertIn("startedAtEpochMs", self.source)
        self.assertIn("hydratePersistedProgress(initialThreadId);", self.source)
        self.assertIn("markPersistedActiveTurnForRecovery", self.source)
        self.assertIn("Restored active work — verifying authoritative thread state", self.source)
        hydrate_at = self.source.index("hydratePersistedProgress(initialThreadId);")
        self.assertLess(hydrate_at, self.source.index("installFetchTap();"))
        self.assertLess(hydrate_at, self.source.index("installSocketTap();"))
        self.assertNotIn("monotonicNow", self.source)
        self.assertNotIn("state.startedAt =", self.source)

    def test_storage_getter_and_rpc_timeout_are_exception_safe(self):
        storage_get = self.source[self.source.index("function storageGet"):self.source.index("function storageSet")]
        self.assertIn("try {", storage_get)
        self.assertGreater(storage_get.index("try {"), storage_get.index("if (!key)"))
        self.assertGreater(storage_get.index("window.localStorage"), storage_get.index("try {"))
        storage_set = self.source[self.source.index("function storageSet"):self.source.index("function sanitizedUpdate")]
        self.assertGreater(storage_set.index("window.localStorage"), storage_set.index("try {"))
        self.assertIn("const RPC_TIMEOUT_MS = 10000", self.source)
        self.assertIn("new window.AbortController()", self.source)
        self.assertIn("controller.abort()", self.source)
        self.assertIn("Promise.race([request, timeout])", self.source)

    def test_events_require_explicit_visible_thread_and_active_turn(self):
        self.assertIn("eventMatchesVisibleThread", self.source)
        self.assertIn("eventBelongsToActiveTurn", self.source)
        self.assertIn("Boolean(visible && incoming && visible === incoming", self.source)
        self.assertIn("if (!incoming) return false", self.source)
        self.assertIn("completedTurns.has(incomingTurnId)", self.source)
        self.assertIn("eventFingerprints", self.source)
        self.assertIn("MAX_EVENT_FINGERPRINTS", self.source)
        self.assertIn("const MAX_PERSISTED_FINGERPRINTS = 2048", self.source)
        self.assertIn("function compactEventFingerprints", self.source)
        self.assertIn("/^[a-f0-9]{16}$/", self.source)
        self.assertNotIn("seenItemEvents", self.source)
        self.assertNotIn("rememberItemEvent", self.source)

    def test_reconciliation_never_fabricates_activity(self):
        reconcile = self.source[
            self.source.index("async function reconcileActiveThread"):
            self.source.index("async function hydrateVisibleThread")
        ]
        self.assertNotIn("state.lastActivityAt = Date.now()", reconcile)
        self.assertNotIn("state.lastRealEventAt = Date.now()", reconcile)
        self.assertIn("handleEvent({", reconcile)
        self.assertIn("'reconcile'", reconcile)
        self.assertIn("rememberEventFingerprint", self.source)

    def test_truthful_panel_and_recovery_surfaces_are_present(self):
        self.assertIn("Latest verified result:", self.source)
        self.assertIn("Next bounded action:", self.source)
        self.assertIn("Technical details", self.source)
        self.assertIn("meaningfulUpdates.slice(-5)", self.source)
        self.assertIn("live $" + "{updateAge}s ago", self.source)
        self.assertIn("NativeEventSource", self.source)
        self.assertIn("openRecoveryEventSource", self.source)
        self.assertIn("scheduleRecoveryEventSource", self.source)
        self.assertIn("recoveryEventSourceTimer", self.source)
        self.assertIn("closed EventSource", (ROOT / "tests" / "progress_overlay_harness.js").read_text(encoding="utf-8"))
        self.assertIn("socket.addEventListener('close'", self.source)
        close_handler = self.source[
            self.source.index("socket.addEventListener('close'"):
            self.source.index("socket.addEventListener('error'")
        ]
        self.assertIn("openRecoveryEventSource();", close_handler)
        self.assertIn("void reconcileActiveThread();", close_handler)
        self.assertIn("No new task event", self.source)
        self.assertIn("Authoritative thread read confirms work is active", self.source)
        self.assertIn("HUMAN_CHECKPOINT_MS = 55000", self.source)
        self.assertNotIn("window.location.reload()", self.source)
        self.assertIn("document.addEventListener('visibilitychange'", self.source)
        self.assertIn("window.addEventListener('pagehide'", self.source)

    def test_terminal_success_requires_substantive_agent_output(self):
        self.assertIn("function substantiveAgentMessage", self.source)
        self.assertIn("function verifyTerminalCompletion", self.source)
        self.assertIn("MAX_RESPONSE_ONLY_RECOVERIES = 3", self.source)
        self.assertIn("original turn is preserved and was not replayed", self.source)
        complete = self.source[
            self.source.index("function completeTurn"):
            self.source.index("function failTurn")
        ]
        self.assertIn("state.hidden = false", complete)
        self.assertNotIn("state.hidden = true", complete)

    def test_lifecycle_recovery_never_creates_or_interrupts_a_turn(self):
        mutating_recovery = self.source[
            self.source.index("async function recoverRepeatedFailureLoop"):
            self.source.index("function handlePlan")
        ]
        self.assertNotIn("rpc('turn/start'", mutating_recovery)
        self.assertNotIn("rpc('turn/interrupt'", mutating_recovery)
        self.assertIn("rpc('thread/read'", mutating_recovery)
        self.assertIn("await reconcileActiveThread()", mutating_recovery)
        self.assertEqual(self.source.count("rpcRequest.method === 'turn/start'"), 1)

    def test_evidence_requires_command_context_and_concrete_readback(self):
        evidence = self.source[
            self.source.index("function verifiedEvidence"):
            self.source.index("function commandFailed")
        ]
        self.assertIn("sha256sum", evidence)
        self.assertIn("apksigner", evidence)
        self.assertIn("package:(\\/", evidence)
        self.assertIn("pm|\\bcodex-pm", evidence)
        self.assertNotIn("Operation returned an explicit Success readback", evidence)
        self.assertNotIn("if (hash)", evidence)
        self.assertNotIn("package:\\S+", evidence)

    def test_raw_path_and_json_transcripts_become_verified_english(self):
        self.assertIn("function humanizeVerboseTranscriptText", self.source)
        self.assertIn("function humanizeVerboseAssistantTranscripts", self.source)
        self.assertIn("function humanizeVerboseFromTextNode", self.source)
        self.assertIn("function humanizeVerboseFromTree", self.source)
        self.assertIn("Verified ${paths.size} automation and development tools", self.source)
        self.assertIn("Gallery scan completed: found ${amount} matching image", self.source)
        self.assertIn("parent.closest('button,pre,code,details,textarea,input')", self.source)
        self.assertIn("humanizeVerboseAssistantTranscripts(added)", self.source)
        self.assertIn("humanizeVerboseFromTree(added)", self.source)
        self.assertIn("const VISUAL_HUMANIZATION_SWEEP_MS = 1000", self.source)
        self.assertIn("humanizeVerboseFromTree(document.body)", self.source)

    def test_redaction_preserves_ordinary_paths_and_repository_state_is_authoritative(self):
        self.assertIn("openrouter\\.env", self.source)
        self.assertIn("<credential-path>", self.source)
        self.assertIn("authoritativeRepositoryState", self.source)
        self.assertIn("authoritativeRepositoryBranch", self.source)
        self.assertIn("Repository ready", self.source)
        self.assertIn("repositoryState === 'none'", self.source)
        self.assertIn("repositoryState === 'detached'", self.source)
        self.assertNotIn("function humanizeRepositoryState", self.source)
        self.assertNotIn("querySelectorAll('*').forEach", self.source)

    def test_possible_side_effects_block_automatic_replay(self):
        self.assertIn("state.possibleSideEffect = true", self.source)
        self.assertIn("Automatic replay blocked after a possible side effect", self.source)
        self.assertIn("if (state.possibleSideEffect)", self.source)
        self.assertIn("turn/interrupt", self.source)

    def test_session_cleanup_is_scoped_backed_up_and_verified(self):
        self.assertIn("function deleteAllSessionsAndThreads", self.source)
        self.assertIn("function backupThreadsForCleanup", self.source)
        self.assertIn("nemotron-session-cleanup-backups", self.source)
        self.assertIn("DELETE ALL SESSIONS AND THREADS", self.source)
        self.assertIn("thread/delete", self.source)
        self.assertIn("active session(s) must finish or be stopped", self.source)
        cleanup = self.source[
            self.source.index("async function deleteAllSessionsAndThreads"):
            self.source.index("function ensureSessionCleanupCard")
        ]
        for forbidden in ("project-root", "removeProject(", "unlink(", "rm -rf", "skills/delete", "settings/write"):
            self.assertNotIn(forbidden, cleanup)

    def test_virtual_webview_harness_covers_runtime_behavior(self):
        completed = subprocess.run(
            ["node", str(ROOT / "tests" / "progress_overlay_harness.js")],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("PROGRESS_OVERLAY_HARNESS_OK", completed.stdout)

    def test_deployed_asset_and_cache_bust_match_source(self):
        self.assertEqual(DEPLOYED_PATH.read_bytes(), SOURCE_PATH.read_bytes())
        version = hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest()[:16]
        expected = f'<script src="/nemotron-autonomy-progress.js?v={version}"></script>'
        self.assertIn(expected, INDEX_PATH.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
