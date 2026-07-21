import pathlib
import os
import contextlib
import hashlib
import io
import json
import re
import runpy
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))
import nemotron_powershell_policy as POWERSHELL_POLICY
import nemotron_android_policy as ANDROID_POLICY


class CapabilityToolchainTests(unittest.TestCase):
    def test_launcher_path_resolves_full_autonomy_surface(self):
        app_path = ":".join((
            str(ROOT / "bin"),
            "/data/data/com.termux/files/usr/bin",
            "/data/data/com.termux/files/home/.local/bin",
        ))
        env = dict(os.environ, PATH=app_path)
        commands = (
            "codex-android", "codex-shizuku", "codex-pm", "codex-search",
            "codex-fetch", "codex-download", "codex-install", "codex-package",
            "codex-open-url", "codex-uninstall", "codex-job", "codex-goal",
            "codex-capability", "codex-artifact", "codex-recover", "codex-browser",
            "codex-ui", "codex-network", "termux-camera-photo",
            "codex-win", "codex-github", "powershell", "pwsh",
            "termux-clipboard-get", "termux-clipboard-set", "termux-location",
            "termux-notification", "termux-battery-status", "termux-vibrate",
            "termux-torch", "termux-volume", "termux-wifi-connectioninfo",
            "termux-tts-speak", "termux-toast", "termux-share", "nmap",
            "python", "node", "rg", "ripgrep",
        )
        for command in commands:
            result = subprocess.run(
                ["/data/data/com.termux/files/usr/bin/bash", "-c", "command -v -- \"$1\"", "_", command],
                cwd=ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
            self.assertEqual(result.returncode, 0, f"{command}: {result.stderr}")
            self.assertTrue(result.stdout.strip(), command)
        rg_path = subprocess.run(
            ["/data/data/com.termux/files/usr/bin/bash", "-c", "command -v rg"],
            cwd=ROOT,
            env=env,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        self.assertEqual(rg_path, str(ROOT / "bin/rg"))
        self.assertIn(
            'exec /data/data/com.termux/files/usr/bin/rg "$@"',
            (ROOT / "bin/rg").read_text(encoding="utf-8"),
        )

    def test_capability_scripts_are_executable_and_have_help(self):
        for relative in (
            "bin/codex-android",
            "bin/codex-pm",
            "bin/codex-wifi-scan",
            "bin/nemotron_wifi_report.py",
            "bin/iwlist",
            "bin/codex-lan-discover",
            "bin/codex-pentest",
            "bin/codex-install",
            "bin/codex-download",
            "bin/codex-package",
            "bin/codex-open-url",
            "bin/codex-shizuku",
            "bin/codex-uninstall",
            "bin/codex-learn",
            "bin/codex-lessons",
            "bin/codex-win",
            "bin/codex-github",
            "bin/powershell",
            "bin/pwsh",
            "bin/rg",
            "bin/ripgrep",
            "bin/curl",
            "bin/wget",
        ):
            script = ROOT / relative
            self.assertTrue(script.stat().st_mode & stat.S_IXUSR, relative)
            result = subprocess.run(
                [str(script), "--help"],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("usage:", result.stdout.lower())

    def test_network_to_shell_execution_is_blocked_before_download(self):
        env = dict(os.environ, PATH=f"{ROOT / 'bin'}:/data/data/com.termux/files/usr/bin")
        safe = subprocess.run(
            ["bash", "-lc", "curl --version"], cwd=ROOT, env=env,
            capture_output=True, text=True, timeout=5, check=False,
        )
        self.assertEqual(safe.returncode, 0, safe.stderr)
        unsafe = subprocess.run(
            ["bash", "-o", "pipefail", "-c", f"{ROOT / 'bin/curl'} -sSf https://example.invalid/installer | sh"],
            cwd=ROOT, env=env, capture_output=True, text=True, timeout=5, check=False,
        )
        self.assertEqual(unsafe.returncode, 126)
        self.assertIn("Blocked unsafe network-to-shell execution", unsafe.stderr)

    def test_pentest_skill_is_syncable(self):
        skill = ROOT / "capabilities/authorized-mobile-pentest/SKILL.md"
        text = skill.read_text(encoding="utf-8")
        self.assertIn("name: Authorized Mobile Pentest", text)
        self.assertIn("CAP_NET_RAW", text)
        self.assertIn("codex-artifact inspect <apk>", text)
        self.assertNotIn("codex-package inspect <apk>", text)
        sync = (ROOT / "sync-capabilities.sh").read_text(encoding="utf-8")
        self.assertIn('find "$SOURCE_DIR" -type f -print0', sync)

    def test_manifest_declares_network_visibility(self):
        manifest = (ROOT / "AndroidManifest.xml").read_text(encoding="utf-8")
        self.assertIn("android.permission.ACCESS_NETWORK_STATE", manifest)
        self.assertNotIn("android.permission.ACCESS_WIFI_STATE", manifest)
        self.assertNotIn("android.permission.CHANGE_WIFI_STATE", manifest)
        self.assertIn('android:networkSecurityConfig="@xml/network_security_config"', manifest)
        self.assertIn('android:usesCleartextTraffic="false"', manifest)
        network = (ROOT / "res/xml/network_security_config.xml").read_text(encoding="utf-8")
        self.assertIn("127.0.0.1", network)
        self.assertIn('cleartextTrafficPermitted="false"', network)

    def test_runtime_trust_is_project_local_and_preflight_enforces_it(self):
        template = (ROOT / "runtime-template/.codex/config.toml").read_text(encoding="utf-8")
        live_path = ROOT / "runtime/.codex/config.toml"
        live = live_path.read_text(encoding="utf-8") if live_path.exists() else template
        preflight = (ROOT / "isolation-preflight.sh").read_text(encoding="utf-8")
        for text in (template, live):
            self.assertNotIn('[projects."/data/data/com.termux/files/home/codex-subscription-isolated-app"]', text)
            self.assertNotIn('[projects."/data/data/com.termux/files/home/nvidia-isolated-app"]', text)
            self.assertNotIn('[projects."/data/data/com.termux/files/home/com.michaelovsky.nemotronunrestricted.isolated"]', text)
            self.assertIn('[projects."/data/data/com.termux/files/home/nemotron-unrestricted-app"]', text)
            self.assertIn('[projects."/data/data/com.termux/files/home/nemotron-unrestricted-app/workspace"]', text)
        self.assertIn("sibling or stale project trust leaked", preflight)
        self.assertIn("credential file mode must be 600", preflight)
        self.assertIn('bootstrap-nemotron-runtime.sh', preflight)
        self.assertIn('endpoint_is_ours', preflight)
        self.assertIn('already healthy (OK)', preflight)
        self.assertIn('already in use by an unverified owner', preflight)
        self.assertIn('PORT_STATE_FILE=', preflight)
        self.assertIn('SAVED_GUI_PORT=', preflight)
        self.assertNotIn('. "$PORT_STATE_FILE"', preflight)

    def test_runtime_bootstrap_creates_only_missing_nonsecret_template_files(self):
        bootstrap = ROOT / "bootstrap-nemotron-runtime.sh"
        with tempfile.TemporaryDirectory(prefix="nemotron-bootstrap-test-") as directory:
            project = pathlib.Path(directory)
            shutil.copytree(ROOT / "runtime-template", project / "runtime-template")
            env = dict(os.environ, NEMOTRON_PROJECT_ROOT=str(project))
            first = subprocess.run(
                ["bash", str(bootstrap)],
                cwd=project,
                env=env,
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertIn("NEMOTRON_RUNTIME_BOOTSTRAP_OK", first.stdout)
            runtime = project / "runtime/.codex"
            config = runtime / "config.toml"
            provider = runtime / "webui-custom-providers.json"
            self.assertTrue(config.is_file())
            self.assertTrue(provider.is_file())
            self.assertEqual(stat.S_IMODE(config.stat().st_mode), 0o600)
            self.assertFalse((runtime / "openrouter.env").exists())
            config.write_text("user-owned-runtime-config\n", encoding="utf-8")
            second = subprocess.run(
                ["bash", str(bootstrap)],
                cwd=project,
                env=env,
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(config.read_text(encoding="utf-8"), "user-owned-runtime-config\n")

    def test_custom_free_mode_configuration_is_normalized_to_the_runtime_provider(self):
        template = (ROOT / "runtime-template/.codex/config.toml").read_text(encoding="utf-8")
        launcher = (ROOT / "nemotron-unrestricted-start.sh").read_text(encoding="utf-8")
        cli = (ROOT / "vendor/codexapp-native-npm/node_modules/codexapp/dist-cli/index.js").read_text(encoding="utf-8")
        self.assertIn('model_provider = "custom"', template)
        self.assertIn('data.get("provider") == "custom"', launcher)
        self.assertIn('CUSTOM_RUNTIME_PROVIDER_ID = "custom_endpoint"', cli)
        self.assertIn('if (state.provider === "custom" && state.customBaseUrl)', cli)
        self.assertIn('`model_provider="${CUSTOM_RUNTIME_PROVIDER_ID}"`', cli)

    def test_release_source_and_secret_gates_are_redacted_and_enforced(self):
        validator = ROOT / "validate-nemotron-sources.sh"
        scanner = ROOT / "scan-nemotron-secrets.py"
        build = (ROOT / "build-nemotron-unrestricted.sh").read_text(encoding="utf-8")
        self.assertTrue(validator.stat().st_mode & stat.S_IXUSR)
        self.assertTrue(scanner.stat().st_mode & stat.S_IXUSR)
        self.assertIn('"$APP_HOME/validate-nemotron-sources.sh"', build)
        self.assertIn('"$APP_HOME/scan-nemotron-secrets.py" --current-only', build)
        self.assertIn('--current-only --apk "$WORK_DIR/$ARTIFACT"', build)
        release_gate = (ROOT / "release-nemotron-gate.sh").read_text(encoding="utf-8")
        self.assertIn('"$APP_HOME/scan-nemotron-secrets.py"', release_gate)
        self.assertIn("--local-private", release_gate)
        self.assertIn('(cd "$APP_HOME/dist" && sha256sum -c --status', release_gate)
        self.assertIn('/certificate SHA-256 digest:/', release_gate)
        self.assertIn("RELEASE_V4_SIDECAR_PRESENT verifier_confirmation_unavailable", release_gate)
        capture = (ROOT / "capture-nemotron-preservation.py").read_text(encoding="utf-8")
        self.assertIn('"--include-sqlite"', capture)
        self.assertIn("if include_sqlite:", capture)

        with tempfile.TemporaryDirectory(prefix="nemotron-secret-scan-") as directory:
            project = pathlib.Path(directory)
            (project / "safe.txt").write_text(
                "OPENROUTER_API_KEY=<YOUR_OPENROUTER_API_KEY>\n", encoding="utf-8"
            )
            clean = subprocess.run(
                [sys.executable, str(scanner), "--root", str(project), "--current-only"],
                cwd=project,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            self.assertEqual(clean.returncode, 0, clean.stderr)
            self.assertIn("SECRET_SCAN_OK", clean.stdout)

            leaked_value = "sk-or" + "-v1-" + "N4f9sQ2wX7kLm3aBc8De1FgH5jKr6TuV"
            (project / "leak.txt").write_text(leaked_value + "\n", encoding="utf-8")
            leaked = subprocess.run(
                [sys.executable, str(scanner), "--root", str(project), "--current-only"],
                cwd=project,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            self.assertEqual(leaked.returncode, 1)
            self.assertIn("OpenRouter API key", leaked.stderr)
            self.assertNotIn(leaked_value, leaked.stderr)

            subprocess.run(["git", "init", "-q"], cwd=project, check=True, timeout=5)
            signing = project / "build/signing.properties"
            signing.parent.mkdir()
            signing.write_text("KEYSTORE_PASSWORD=not-a-real-password\n", encoding="utf-8")
            subprocess.run(["git", "add", "build/signing.properties"], cwd=project, check=True, timeout=5)
            staged = subprocess.run(
                [sys.executable, str(scanner), "--root", str(project), "--current-only"],
                cwd=project,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            self.assertEqual(staged.returncode, 1)
            self.assertIn("staged signing material path", staged.stderr)
            self.assertNotIn("not-a-real-password", staged.stderr)

    def test_preservation_gate_verifies_hashes_and_emits_only_private_safe_summary(self):
        verifier = ROOT / "verify-nemotron-preservation.sh"
        self.assertTrue(verifier.stat().st_mode & stat.S_IXUSR)
        with tempfile.TemporaryDirectory(prefix="nemotron-preservation-") as directory:
            project = pathlib.Path(directory)
            state = project / "runtime/.codex"
            session = state / "sessions/thread.jsonl"
            session.parent.mkdir(parents=True)
            session.write_text(
                json.dumps({
                    "type": "session_meta",
                    "payload": {"session_id": "thread-private", "cwd": "/private/project"},
                }) + "\n",
                encoding="utf-8",
            )
            (state / "archived_sessions").mkdir()
            (state / "workspace").mkdir()
            connection = sqlite3.connect(state / "state_5.sqlite")
            connection.execute("CREATE TABLE state (thread_id TEXT, project_root TEXT)")
            connection.execute("INSERT INTO state VALUES (?, ?)", ("thread-private", "/private/project"))
            connection.commit()
            connection.close()
            digest = hashlib.sha256(session.read_bytes()).hexdigest()
            manifest = project / "before.sha256"
            manifest.write_text(f"{digest}  runtime/.codex/sessions/thread.jsonl\n", encoding="utf-8")

            verified = subprocess.run(
                [str(verifier), "--manifest", str(manifest), "--cwd", str(project), "--state-root", str(state)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            self.assertEqual(verified.returncode, 0, verified.stderr)
            self.assertIn("PRESERVATION_MANIFEST_OK entries=1", verified.stdout)
            self.assertIn("PRESERVATION_STATE_OK", verified.stdout)
            self.assertIn("unique_threads=1", verified.stdout)
            self.assertNotIn("thread-private", verified.stdout)
            self.assertNotIn("/private/project", verified.stdout)

            session.write_text("changed\n", encoding="utf-8")
            mismatch = subprocess.run(
                [str(verifier), "--manifest", str(manifest), "--cwd", str(project), "--state-root", str(state)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            self.assertEqual(mismatch.returncode, 1)
            self.assertIn("PRESERVATION_MANIFEST_MISMATCH", mismatch.stderr)
            self.assertNotIn("thread-private", mismatch.stderr)

    def test_toolchain_lists_core_packages(self):
        packages = (ROOT / "toolchain/termux-packages.txt").read_text(encoding="utf-8")
        for package in (
            "openssl-tool", "dnsutils", "ripgrep", "yara", "radare2", "apktool",
            "golang", "rust", "cmake", "zip", "p7zip",
        ):
            self.assertIn(package, packages)

    def test_machine_readable_capability_matrix_is_strict_and_complete(self):
        matrix = json.loads((ROOT / "capabilities/capability-matrix.json").read_text(encoding="utf-8"))
        self.assertEqual(matrix["schemaVersion"], 1)
        identifiers = {entry["id"] for entry in matrix["capabilities"]}
        self.assertTrue({
            "web-research", "browser-automation", "download-install",
            "android-ui-device", "paired-windows-github", "durable-jobs-recovery",
            "native-code-toolchains", "archives-files", "network-debug-static-analysis",
        }.issubset(identifiers))
        serialized = json.dumps(matrix, sort_keys=True)
        for command in ("codex-search", "codex-install", "codex-android", "go", "cargo", "cmake", "7z"):
            self.assertIn(f'"{command}"', serialized)
        for unsupported in (
            "captcha-bypass", "credential-or-clipboard-theft", "malware-evasion",
            "reverse-shell-payloads", "unrooted-docker-in-docker-guarantee",
        ):
            self.assertIn(unsupported, matrix["unsupportedClaims"])

    def test_exact_dolphin_windows_endpoint_is_checksum_and_tailnet_scoped(self):
        setup = (ROOT / "windows/setup-dolphin-x1-server.ps1").read_text(encoding="utf-8")
        start = (ROOT / "windows/start-dolphin-x1-server.ps1").read_text(encoding="utf-8")
        self.assertIn("2387a10ceb3f236c5525985bafef1e6c8430ce3f7a32d980a413121941179e84", setup)
        self.assertIn("a6d0cde87f086f20f48d5ad85860807cd8bc57c5fa2f7b534a6434a33ec6bd83", setup)
        self.assertIn('RemoteAddress "100.64.0.0/10"', setup)
        self.assertIn('TaskName "Nemotron-Dolphin-X1-405B"', setup)
        self.assertIn('"--alias", "dphn/Dolphin-X1-Llama-3.1-405B"', start)
        self.assertIn('"--fit", "on"', start)
        self.assertIn('"--fit-target", "2048"', start)
        self.assertNotIn("0.0.0.0", start)

    def test_wifi_contract_has_bounded_failure_rules(self):
        skill = (ROOT / "capabilities/authorized-mobile-pentest/SKILL.md").read_text(encoding="utf-8")
        contract = (ROOT / "capabilities/NEMOTRON_AGENT_CONTRACT.md").read_text(encoding="utf-8")
        self.assertIn("Never call `cmd wifi start-scan`", skill)
        self.assertIn("identical failed command more than three times", skill)
        self.assertIn("three-second intervals", contract)
        self.assertIn("explicitly authorized target", contract)

    def test_healthy_runtime_refreshes_capabilities_before_exit(self):
        launcher = (ROOT / "nemotron-unrestricted-start.sh").read_text(encoding="utf-8")
        healthy_branch = launcher.split("healthy_existing_runtime", 2)[2].split("fi", 1)[0]
        self.assertIn("refresh_runtime_capabilities", healthy_branch)
        self.assertIn('[ -s "$PROXY_HASH_FILE" ]', launcher)
        self.assertIn('[ -s "$SUPERVISOR_HASH_FILE" ]', launcher)
        self.assertIn('health.get("app") == "nemotron-unrestricted"', launcher)
        self.assertIn('health.get("sourceSha256") == expected_hash', launcher)
        self.assertIn('health.get("supervisorSourceHash") == expected_supervisor_hash', launcher)

    def test_launcher_embedded_python_blocks_compile(self):
        launcher = (ROOT / "nemotron-unrestricted-start.sh").read_text(encoding="utf-8")
        blocks = re.findall(r"<<'PY'\n(.*?)\nPY", launcher, flags=re.DOTALL)
        self.assertGreaterEqual(len(blocks), 5)
        for index, block in enumerate(blocks):
            try:
                compile(block, f"launcher-heredoc-{index}", "exec")
            except SyntaxError as error:
                self.fail(f"embedded Python block {index} does not compile: {error}")

    def test_local_install_and_package_shims_handle_shizuku_streams(self):
        installer = (ROOT / "bin/codex-install").read_text(encoding="utf-8")
        package = (ROOT / "bin/codex-package").read_text(encoding="utf-8")
        policy = (ROOT / "bin/nemotron_android_policy.py").read_text(encoding="utf-8")
        self.assertIn("pm install --user 0 -r -S", installer)
        self.assertIn("input_path=target", installer)
        self.assertIn("package_evidence", package)
        self.assertIn("pm path --user 0", policy)
        self.assertIn("result.combined", policy)
        self.assertIn("__NEMOTRON_REMOTE_STATUS_", policy)

    def test_android_control_and_package_mutations_guard_protected_apps(self):
        android = (ROOT / "bin/codex-android").read_text(encoding="utf-8")
        installer = (ROOT / "bin/codex-install").read_text(encoding="utf-8")
        uninstaller = (ROOT / "bin/codex-uninstall").read_text(encoding="utf-8")
        package_manager = (ROOT / "bin/codex-pm").read_text(encoding="utf-8")
        for protected in (
            "com.michaelovsky.codexapplauncher",
            "com.michaelovsky.codexsubscription.isolated",
            "com.michaelovsky.codexnvidia.isolated",
            "com.termux",
            "moe.shizuku.privileged.api",
        ):
            self.assertIn(protected, (ROOT / "bin/nemotron_android_policy.py").read_text(encoding="utf-8"))
        for wrapper in (android, installer, uninstaller, package_manager):
            self.assertIn("nemotron_android_policy", wrapper)
        self.assertIn('action == "open"', android)
        self.assertIn("resumed_component", android)
        self.assertIn("fresh-top-resumed-activity", android)
        self.assertIn("validate_pm_arguments", package_manager)

    def test_shizuku_status_stage_and_test_are_real_privilege_checks(self):
        wrapper = (ROOT / "bin/codex-shizuku").read_text(encoding="utf-8")
        self.assertIn('{"status", "stage", "test"}', wrapper)
        self.assertIn('"uid=2000(shell)"', wrapper)
        self.assertIn('"isolated-shizuku-rish"', wrapper)

    def test_autonomy_contract_executes_instead_of_promising_manual_work(self):
        contract = (ROOT / "capabilities/NEMOTRON_AGENT_CONTRACT.md").read_text(encoding="utf-8")
        self.assertIn("do not answer with future-tense promises", contract)
        self.assertIn("Never ask the user to search, download, install, open an app", contract)
        self.assertIn("Do not invent subcommands from ordinary English verbs", contract)
        self.assertIn("`codex-android launch` is invalid", contract)
        self.assertIn("codex-android open <package>", contract)
        self.assertIn("codex-pm path <resolved-package>", contract)
        self.assertNotIn("codex-android current|packages|launch|shell", contract)
        self.assertIn("verify checksum/package/signature", contract)
        self.assertIn("read back package path/version/hash", contract)
        self.assertIn("unverified no-op", contract)
        self.assertIn("Never answer that internet browsing, downloading, APK installation", contract)
        self.assertIn("A direct URL is optional", contract)
        self.assertIn("Capability discovery is local-first", contract)
        self.assertIn("A capability answer without a real `exec_command` result", contract)
        self.assertIn("A `SKILL.md` path is documentation, never proof", contract)
        self.assertIn("`codex-install` has no `--overwrite` requirement", contract)
        self.assertIn("Never infer local capability from web-search results", contract)
        self.assertIn("omit `sandbox_permissions`", contract)
        self.assertIn("Never invent joined placeholders", contract)
        self.assertIn("Do not ask whether to demonstrate", contract)
        self.assertIn("Do not implement malware evasion", contract)
        template = (ROOT / "runtime-template/.codex/config.toml").read_text(encoding="utf-8")
        self.assertIn("Installed surfaces include codex-search, codex-fetch, codex-download", template)
        self.assertIn("any capability answer without a real exec_command result", template)
        self.assertIn("Never treat SKILL.md as an executable", template)
        self.assertIn("Before prose, omit sandbox_permissions and run: command -v", template)
        self.assertIn("omit sandbox_permissions entirely", template)
        self.assertIn("Never infer local capability from web-search results", template)
        self.assertIn("Do not ask the user to supply commands", template)

    def test_windows_and_github_use_the_global_credential_broker(self):
        windows = (ROOT / "bin/codex-win").read_text(encoding="utf-8")
        github = (ROOT / "bin/codex-github").read_text(encoding="utf-8")
        powershell = (ROOT / "bin/powershell").read_text(encoding="utf-8")
        contract = (ROOT / "capabilities/NEMOTRON_AGENT_CONTRACT.md").read_text(encoding="utf-8")
        self.assertIn('/data/data/com.termux/files/home/.codex', windows)
        self.assertIn('/data/data/com.termux/files/home/.local/bin/codex-win', windows)
        self.assertIn('attempts = 3 if is_status else 1', windows)
        self.assertIn('except subprocess.TimeoutExpired', windows)
        self.assertIn('process_timeout = gateway_timeout + 15', windows)
        self.assertIn('response.get("verified") is True', windows)
        self.assertIn('powershell_github_status', github)
        self.assertIn('"--timeout", "15"', github)
        self.assertNotIn('authSummary', github)
        self.assertNotIn('gh auth token', github)
        self.assertIn('codex-win', contract)
        self.assertIn('codex-github status', contract)
        self.assertIn('codex-github run', contract)
        self.assertIn('Never export GitHub tokens', contract)
        self.assertIn('compatibility_payload', powershell)
        self.assertIn('prepare_gateway_payload', windows)
        self.assertIn('fail-closed read-only validator', contract)
        self.assertIn('inventory → classify → exclude → manifest → execute → verify', contract)
        build = (ROOT / "build-nemotron-unrestricted.sh").read_text(encoding="utf-8")
        self.assertIn('bin/nemotron_powershell_policy.py', build)
        self.assertIn('compile(source.read_text', build)

    def test_powershell_compatibility_argument_forms_are_exact(self):
        for prefix in (("-Command",), ("-c",), ("-lc",), ("-l", "-c")):
            payload = POWERSHELL_POLICY.compatibility_payload((*prefix, "Get-PSDrive"))
            self.assertEqual(payload, {"action": "powershell", "command": "Get-PSDrive"})
        for arguments in (
            (),
            ("Get-PSDrive",),
            ("-Command",),
            ("-Command", "Get-Date", "extra"),
            ("-l", "-Command", "Get-Date"),
            ("-EncodedCommand", "RwBlAHQALQBEAGEAdABlAA=="),
            ("-enc", "RwBlAHQALQBEAGEAdABlAA=="),
            ("-File", "task.ps1"),
            ("-Command", "-"),
        ):
            with self.subTest(arguments=arguments):
                with self.assertRaises(POWERSHELL_POLICY.PolicyViolation):
                    POWERSHELL_POLICY.compatibility_payload(arguments)

    def test_powershell_rejects_dynamic_nested_and_deletion_commands(self):
        dynamic_or_nested = (
            "Invoke-Expression $payload",
            "iex $payload",
            "[ScriptBlock]::Create($payload).Invoke()",
            "[Convert]::FromBase64String($payload)",
            "$ExecutionContext.InvokeCommand.InvokeScript($payload)",
            "$type.InvokeMember('Delete', $flags, $null, $target, @())",
            "$object.InvokeMethod('Delete', @())",
            "Invoke-Member Delete",
            "ForEach-Object -MemberName $member",
            "Get-ChildItem C:\\Temp | ForEach-Object -MemberName Delete",
            "% -MethodName $method",
            "Get-ChildItem C:\\Temp | % -MethodName Delete",
            "ForEach-Object { . $scriptPath }",
            "if ($enabled) { . $scriptPath }",
            "powershell.exe -EncodedCommand RwBlAHQALQBEAGEAdABlAA==",
            "pwsh -c 'Get-Date'",
            "cmd.exe /c echo unsafe",
            "cmd.exe /q /c echo unsafe",
            "Start-Process powershell.exe",
            "& $command",
            "python -c 'print(1)'",
            "python delete_files.py",
        )
        deletion_commands = (
            r"Remove-Item -LiteralPath C:\Temp\x -Recurse -Force",
            r"ri -r -fo C:\Temp\x",
            r"rm -r C:\Temp\x",
            r"del /s /q C:\Temp\x",
            r"rd /s /q C:\Temp\x",
            r"cmd /c rmdir /s /q C:\Temp\x",
            r"[IO.File]::Delete('C:\Temp\x')",
            r"[IO.Directory]::Delete('C:\Temp\x', $true)",
            r"$item.Delete()",
            r"$fso.DeleteFolder('C:\Temp\x')",
            r"Get-ChildItem C:\Temp | ForEach-Object Delete",
            r"Get-ChildItem C:\Temp | % Delete",
            r"unlink C:\Temp\x",
            r"Clear-Content -LiteralPath C:\Temp\x",
            r"robocopy C:\Empty C:\Target /MIR",
            r"git clean -fdx",
            r"reg.exe delete HKCU\Software\Vendor /f",
            r"Remove-CimInstance -InputObject $item",
            r"Remove-AppxPackage Vendor.App",
            r"Set-Content -LiteralPath C:\Temp\x -Value ''",
            r"[IO.File]::WriteAllText('C:\Temp\x','')",
            r"Clear-ItemProperty -Path HKCU:\Software\Vendor -Name X",
            r"Move-Item C:\Temp\x C:\Temp\y",
            r"Set-ItemProperty -Path HKCU:\Software\Vendor -Name X -Value Y",
            r"format.com D: /q",
            r"shutdown.exe /s /t 0",
            r"Stop-Computer",
            r"Restart-Computer",
        )
        for command in (*dynamic_or_nested, *deletion_commands):
            with self.subTest(command=command):
                with self.assertRaises(POWERSHELL_POLICY.PolicyViolation):
                    POWERSHELL_POLICY.validate_powershell_command(command)
        self.assertEqual(
            POWERSHELL_POLICY.validate_powershell_command("Get-PSDrive | Select-Object Name,Free"),
            "Get-PSDrive | Select-Object Name,Free",
        )
        self.assertEqual(
            POWERSHELL_POLICY.validate_powershell_command("gh --version"),
            "gh --version",
        )
        self.assertEqual(
            POWERSHELL_POLICY.validate_github_command("gh pr view 1 --json title,state"),
            "gh pr view 1 --json title,state",
        )
        for command in ("gh auth token", "git clean -fdx", "git reset --hard HEAD", "gh pr list | Out-String"):
            with self.subTest(github_command=command):
                with self.assertRaises(POWERSHELL_POLICY.PolicyViolation):
                    POWERSHELL_POLICY.validate_github_command(command)

    def test_structured_cleanup_validates_paths_and_classifications(self):
        allowed = (
            (r"C:\Users\Alice\AppData\Local\Vendor\Cache", "cache"),
            (r"C:\Users\Alice\AppData\Local\Temp\codex-disposable-123", "temp"),
            (r"D:\Downloads\widget-installer-1.0.msi", "redundant-installer"),
            (r"D:\Scratch\codex-disposable-123", "disposable"),
        )
        request = {
            "action": "powershell_cleanup",
            "targets": [{"path": path, "classification": classification} for path, classification in allowed],
        }
        self.assertEqual(POWERSHELL_POLICY.validate_cleanup_request(request), request)

        blocked_paths = (
            "C:\\",
            "D:\\",
            r"\\server\share\Temp\x",
            r"Temp\x",
            r"$env:TEMP\x",
            r"C:\Temp\*",
            r"C:\Windows\Temp\x",
            r"C:\Program Files\Vendor\Cache",
            r"C:\Program Files (x86)\Vendor\Cache",
            r"C:\PROGRA~1\Vendor\Cache",
            r"C:\ProgramData\Vendor\Cache",
            r"C:\Users",
            r"C:\Users\Alice",
            r"C:\Users\Alice\AppData",
            r"C:\Users\Alice\AppData\Local",
            r"C:\Users\Alice\.ssh\Cache",
            r"C:\Users\Alice\AppData\Roaming\Microsoft\Credentials\Cache",
            r"C:\Users\Alice\Scratch\.git-credentials",
            r"D:\Projects\Product\Cache",
        )
        for path in blocked_paths:
            with self.subTest(path=path):
                with self.assertRaises(POWERSHELL_POLICY.PolicyViolation):
                    POWERSHELL_POLICY.validate_cleanup_request({
                        "action": "powershell_cleanup",
                        "targets": [{"path": path, "classification": "cache"}],
                    })
        with self.assertRaises(POWERSHELL_POLICY.PolicyViolation):
            POWERSHELL_POLICY.validate_cleanup_request({
                "action": "powershell_cleanup",
                "targets": [{"path": r"D:\Downloads\notes.txt", "classification": "redundant-installer"}],
            })
        with self.assertRaises(POWERSHELL_POLICY.PolicyViolation):
            POWERSHELL_POLICY.validate_cleanup_request({
                "action": "powershell_cleanup",
                "targets": [{"path": allowed[0][0], "classification": "cache", "manifest": True}],
            })
        with self.assertRaises(POWERSHELL_POLICY.PolicyViolation):
            POWERSHELL_POLICY.validate_cleanup_request({
                "action": "powershell_cleanup",
                "targets": [
                    {"path": r"C:\Users\Alice\AppData\Local\Temp\codex-disposable-123", "classification": "temp"},
                    {"path": r"C:\Users\Alice\AppData\Local\Temp\codex-disposable-123\child.tmp", "classification": "temp"},
                ],
            })

    def test_cleanup_script_has_fixed_phase_order_and_immediate_recheck(self):
        request = POWERSHELL_POLICY.validate_cleanup_request({
            "action": "powershell_cleanup",
            "targets": [{
                "path": r"C:\Users\Alice\AppData\Local\Temp\codex-disposable-123",
                "classification": "temp",
            }],
        })
        script = POWERSHELL_POLICY.build_cleanup_script(request["targets"])
        offsets = [script.index(f"# phase: {phase}") for phase in POWERSHELL_POLICY.CLEANUP_PHASES]
        self.assertEqual(offsets, sorted(offsets))
        self.assertIn("Get-Item -LiteralPath", script)
        self.assertIn("$Manifest =", script)
        self.assertIn("Remove-Item -LiteralPath", script)
        execute = script.index("# phase: execute")
        recheck = script.index("Immediate exclusion/classification/readback recheck", execute)
        current_item = script.index("$Current = Get-Item -LiteralPath", recheck)
        current_children = script.index("$CurrentChildren = @(Get-ChildItem -LiteralPath $Current.FullName", current_item)
        current_bound = script.index("$CurrentChildren.Count -gt $MaximumChildrenPerTarget", current_children)
        current_reparse = script.index("$CurrentChildren | Where-Object", current_bound)
        deletion = script.index("Remove-Item -LiteralPath", execute)
        self.assertLess(recheck, current_item)
        self.assertLess(current_item, current_children)
        self.assertLess(current_children, current_bound)
        self.assertLess(current_bound, current_reparse)
        self.assertLess(current_reparse, deletion)
        self.assertIn("Select-Object -First ($MaximumChildrenPerTarget + 1)", script[current_children:deletion])
        self.assertIn("Test-Path -LiteralPath", script[script.index("# phase: verify"):])
        self.assertIn("Test-PathChainSafe", script)
        self.assertIn("$Receipts +=", script)
        self.assertIn("receipts = $Receipts", script)
        self.assertIn("completedCount = $Receipts.Count", script)

    def test_direct_codex_win_cannot_bypass_policy_and_cleanup_is_transformed(self):
        for command in (
            r"Remove-Item C:\Temp\x -Recurse",
            "Invoke-Expression $payload",
            "cmd /c rd /s C:\\Temp\\x",
        ):
            with self.subTest(command=command):
                with self.assertRaises(POWERSHELL_POLICY.PolicyViolation):
                    POWERSHELL_POLICY.prepare_gateway_payload(json.dumps({
                        "action": "powershell", "command": command,
                    }))
        cleanup = {
            "action": "powershell_cleanup",
            "targets": [{
                "path": r"C:\Users\Alice\AppData\Local\Temp\codex-disposable-123",
                "classification": "temp",
            }],
        }
        transformed = json.loads(POWERSHELL_POLICY.prepare_gateway_payload(json.dumps(cleanup)))
        self.assertEqual(transformed["action"], "powershell")
        self.assertIn("# phase: inventory", transformed["command"])
        self.assertIn("Remove-Item -LiteralPath", transformed["command"])

    def test_powershell_and_codex_win_safe_routes_are_mocked(self):
        wrapper = runpy.run_path(str(ROOT / "bin/powershell"), run_name="powershell_wrapper_test")
        with mock.patch.object(wrapper["subprocess"], "call", return_value=0) as gateway_call:
            with mock.patch.object(sys, "argv", [str(ROOT / "bin/powershell"), "-c", "Get-PSDrive"]):
                self.assertEqual(wrapper["main"](), 0)
        invocation = gateway_call.call_args.args[0]
        self.assertEqual(invocation[0], str(ROOT / "bin/codex-win"))
        self.assertEqual(json.loads(invocation[1]), {"action": "powershell", "command": "Get-PSDrive"})

        broker = runpy.run_path(str(ROOT / "bin/codex-win"), run_name="codex_win_wrapper_test")
        completed = subprocess.CompletedProcess(
            [], 0, json.dumps({"ok": True, "verified": True, "exitCode": 0}), ""
        )
        with mock.patch.object(broker["subprocess"], "run", return_value=completed) as global_gateway:
            with mock.patch.object(sys, "argv", [
                str(ROOT / "bin/codex-win"),
                json.dumps({"action": "powershell", "command": "Get-PSDrive"}),
            ]):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(broker["main"](), 0)
        forwarded = json.loads(global_gateway.call_args.args[0][1])
        self.assertEqual(forwarded, {"action": "powershell", "command": "Get-PSDrive"})
        self.assertEqual(global_gateway.call_args.kwargs["timeout"], 75)

        unverified = subprocess.CompletedProcess(
            [], 0, json.dumps({"ok": True, "verified": False, "exitCode": 0}), ""
        )
        with mock.patch.object(broker["subprocess"], "run", return_value=unverified):
            with mock.patch.object(sys, "argv", [
                str(ROOT / "bin/codex-win"),
                json.dumps({"action": "powershell", "command": "Get-PSDrive"}),
                "--timeout", "120",
            ]):
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(broker["main"](), 5)

        status_receipt = subprocess.CompletedProcess([], 0, json.dumps({
            "ok": True, "verified": False, "exitCode": 0,
            "companion": "CODEX_PC_BRIDGE_READY",
            "gateway": "CODEX_WINDOWS_AUTONOMY_GATEWAY_READY",
            "computer": "WORKSTATION", "user": "operator", "elevated": True,
            "port": 18767, "tailnetAddress": "100.64.0.2", "time": "2026-07-21T00:00:00Z",
            "policy": {"interactiveApprovalRequired": False, "readOnlyActions": ["status"], "stateChangingActions": ["powershell"]},
        }), "")
        with mock.patch.object(broker["subprocess"], "run", return_value=status_receipt):
            with mock.patch.object(sys, "argv", [str(ROOT / "bin/codex-win"), json.dumps({"action": "status"})]):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(broker["main"](), 0)

        with mock.patch.object(broker["subprocess"], "run") as blocked_gateway:
            with mock.patch.object(sys, "argv", [
                str(ROOT / "bin/codex-win"),
                json.dumps({"action": "powershell", "command": r"rm -r C:\Temp\x"}),
            ]):
                self.assertEqual(broker["main"](), 64)
        blocked_gateway.assert_not_called()
        with mock.patch.object(broker["subprocess"], "run") as ambiguous_gateway:
            with mock.patch.object(sys, "argv", [
                str(ROOT / "bin/codex-win"),
                json.dumps({"action": "powershell", "command": "Get-PSDrive"}),
                "--unexpected",
            ]):
                self.assertEqual(broker["main"](), 64)
        ambiguous_gateway.assert_not_called()

    def test_pwsh_forwards_to_the_same_policy_without_a_gateway(self):
        with tempfile.TemporaryDirectory() as temporary:
            sandbox = pathlib.Path(temporary)
            shutil.copy2(ROOT / "bin/pwsh", sandbox / "pwsh")
            policy_bin = repr(str(ROOT / "bin"))
            mock_powershell = sandbox / "powershell"
            mock_powershell.write_text(
                f"#!{sys.executable}\n"
                "import sys\n"
                f"sys.path.insert(0, {policy_bin})\n"
                "from nemotron_powershell_policy import PolicyViolation, compatibility_payload\n"
                "try:\n"
                "    compatibility_payload(sys.argv[1:])\n"
                "except PolicyViolation:\n"
                "    raise SystemExit(64)\n",
                encoding="utf-8",
            )
            mock_powershell.chmod(mock_powershell.stat().st_mode | stat.S_IXUSR)
            blocked = subprocess.run(
                [str(sandbox / "pwsh"), "-EncodedCommand", "RwBlAHQALQBEAGEAdABlAA=="],
                cwd=ROOT, capture_output=True, text=True, timeout=5, check=False,
            )
            safe = subprocess.run(
                [str(sandbox / "pwsh"), "-lc", "Get-PSDrive"],
                cwd=ROOT, capture_output=True, text=True, timeout=5, check=False,
            )
        self.assertEqual(blocked.returncode, 64)
        self.assertEqual(safe.returncode, 0)

    def test_visible_url_wrapper_uses_privileged_verified_intent(self):
        wrapper = (ROOT / "bin/codex-open-url").read_text(encoding="utf-8")
        self.assertIn("am start -W -a android.intent.action.VIEW", wrapper)
        self.assertNotIn("exec termux-open-url", wrapper)

    def test_web_overlay_uses_content_hash_cache_busting(self):
        source = ROOT / "web/nemotron-autonomy-progress.js"
        version = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
        expected = f'<script src="/nemotron-autonomy-progress.js?v={version}"></script>'
        index = (ROOT / "vendor/codexapp-native-npm/node_modules/codexapp/dist/index.html").read_text(encoding="utf-8")
        sync = (ROOT / "sync-nemotron-web.sh").read_text(encoding="utf-8")
        preflight = (ROOT / "isolation-preflight.sh").read_text(encoding="utf-8")
        self.assertIn(expected, index)
        self.assertIn("ASSET_VERSION=$(sha256sum", sync)
        self.assertIn("WEB_ASSET_VERSION=$(sha256sum", preflight)

    def test_runtime_ports_are_dynamic_and_propagated(self):
        launcher = (ROOT / "nemotron-unrestricted-start.sh").read_text(encoding="utf-8")
        proxy = (ROOT / "nemotron_unrestricted_proxy.py").read_text(encoding="utf-8")
        supervisor = (ROOT / "nemotron_session_supervisor.py").read_text(encoding="utf-8")
        preflight = (ROOT / "isolation-preflight.sh").read_text(encoding="utf-8")
        self.assertIn('PORT=$(select_port "$DEFAULT_GUI_PORT")', launcher)
        self.assertIn('PROXY_PORT=$(select_port "$DEFAULT_PROXY_PORT" "$PORT")', launcher)
        self.assertIn('SUPERVISOR_PORT=$(select_port "$DEFAULT_SUPERVISOR_PORT" "$PORT" "$PROXY_PORT")', launcher)
        self.assertIn('export NEMOTRON_GUI_PORT="$PORT" NEMOTRON_PROXY_PORT="$PROXY_PORT"', launcher)
        self.assertIn('data["customBaseUrl"] = f"http://127.0.0.1:{port}/v1"', launcher)
        self.assertIn('configured_port("NEMOTRON_PROXY_PORT", 18774)', proxy)
        self.assertIn('configured_port("NEMOTRON_GUI_PORT", 5903)', proxy)
        self.assertIn('configured_port("NEMOTRON_SUPERVISOR_PORT", 18775)', supervisor)
        self.assertIn("codex-android", preflight)

    def test_android_recovery_and_state_preservation_contract(self):
        activity = (ROOT / "src/com/michaelovsky/nemotronunrestricted/isolated/MainActivity.java").read_text(encoding="utf-8")
        service = (ROOT / "src/com/michaelovsky/nemotronunrestricted/isolated/NemotronRuntimeService.java").read_text(encoding="utf-8")
        manifest = (ROOT / "AndroidManifest.xml").read_text(encoding="utf-8")
        self.assertIn("onRenderProcessGone", activity)
        self.assertIn("recoverGui", activity)
        self.assertIn("discoverRuntimePort", activity)
        self.assertIn("postVisualStateCallback", activity)
        self.assertIn("MAIN_FRAME_TIMEOUT_MS", activity)
        self.assertIn("while (!destroyed)", activity)
        self.assertNotIn("attempt < 90", activity)
        self.assertIn("rememberRoute", activity)
        self.assertIn("restoredRouteSuffix", activity)
        self.assertIn("sessions and projects preserved", activity)
        self.assertIn("shouldOverrideUrlLoading", activity)
        self.assertIn("isTrustedRuntimeUri", activity)
        self.assertIn("request.getOrigin()", activity)
        self.assertIn("bridgeToken", activity)
        self.assertIn("missionComplete", activity)
        self.assertIn("sanitizeCompletionPayload", activity)
        self.assertIn("supervisorIsOurs(discoveredSupervisor, discoveredSupervisorHash)", activity)
        self.assertIn("isOurSupervisor(supervisorPort, supervisorSourceHash)", service)
        self.assertIn("START_STICKY", service)
        self.assertIn("scheduleWithFixedDelay", service)
        self.assertIn('android:stopWithTask="false"', manifest)
        self.assertIn("android.intent.action.BOOT_COMPLETED", manifest)
        self.assertIn("android.intent.action.MY_PACKAGE_REPLACED", manifest)
        self.assertIn("Build.VERSION.SDK_INT >= 26", (ROOT / "src/com/michaelovsky/nemotronunrestricted/isolated/BootReceiver.java").read_text(encoding="utf-8"))
        self.assertIn('android:configChanges="keyboard|keyboardHidden|orientation|screenSize|smallestScreenSize|uiMode"', manifest)
        self.assertIn('android:allowBackup="false"', manifest)


if __name__ == "__main__":
    unittest.main()
