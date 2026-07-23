# Nemotron Unrestricted — authoritative new-session handoff

## Read this first

This document is the continuation contract for `/data/data/com.termux/files/home/nemotron-unrestricted-app`. A new session must read it completely before changing, rebuilding, restarting, installing, or opening anything. Preserve all existing user projects, conversations, memories, credentials, runtime data, and intentional uncommitted changes. Do not uninstall the package, clear package data, delete `.codex`, replace the runtime home, restart a completed turn, or silently substitute a model.

The mission is to finish and verify a durable Android AI-agent application that maximizes autonomous, tool-first execution for lawful user-authorized work: coding, research, web/API use, downloads, verified installation, Android automation, gallery operations, paired-PC work, Git/GitHub work, long-running background tasks, multimodal input/output, and authorized defensive security testing. “Unrestricted” means the application should not add arbitrary refusals, generic capability disclaimers, fake progress, or needless manual handoffs when an installed tool can lawfully perform the action. It does **not** authorize malware, credential theft, unauthorized intrusion, covert surveillance, authentication/CAPTCHA bypass, security evasion, destructive attacks, or actions outside the user’s authority. Never claim that provider limits, Android protections, account authentication, hardware limits, or physical-user-presence requirements can be removed.

Continue until every applicable acceptance gate below is verified, the user explicitly stops the work, or a genuine external authorization/platform/hardware gate remains after safe alternatives are exhausted. A genuine gate must be reported precisely with preserved progress; never invent success and never loop or restart work from the beginning.

## Resume exactly here — authoritative stopping point

**Handoff refreshed:** 2026-07-21. This is not a blank project and not a request to rebuild from scratch. The previous session stopped after implementing the current Android/proxy/model-routing changes, passing the recorded initial test/build gates, reinstalling the rebuilt APK while preserving package data, collecting live/package/Windows/Git evidence, and writing this handoff. The handoff itself was the final action. No app UI launch, isolated-runtime restart, Windows download resume, Git commit, remote creation, push, or GitHub release was performed afterward.

The exact current state is:

- **Completed and preserved:** source changes listed below; conditional exact-Dolphin proxy routing; Tailscale-only launcher discovery; Windows setup/start scripts; initial 174-test pass; progress-overlay harness; source validation; secret scans; APK build; data-preserving APK reinstall; installed-package and preservation evidence.
- **Installed but deliberately not opened:** the rebuilt APK. Do not open it merely to orient yourself.
- **Still running from the older deployed source:** the isolated GUI/proxy/supervisor. Its healthy old-source endpoints are baseline evidence, not proof that edited proxy/launcher code is active.
- **First unfinished local implementation lane:** after the mandatory read-only revalidation, continue at plan step 21 by auditing `nemotron-unrestricted-start.sh`, then proceed through the remaining local Android/runtime/source/test/build steps in order.
- **First unfinished Windows mutation:** plan step 79, resuming the two existing partial Dolphin X1 shard downloads. Steps 76–78 are read-only safety revalidation immediately before it.
- **Intentionally deferred:** every Windows mutation remains after the local Android/offline gates, exactly as the user requested.
- **Approval-gated:** Git remote creation, GitHub repository creation, push, public release, and release-asset upload remain forbidden until the user explicitly approves publishing after final local acceptance.
- **Final activation point:** restart only the isolated Nemotron runtime at plan step 92, after local and Windows model gates pass. Open the Android UI only at step 99 after every applicable prelaunch gate passes.

### Mandatory first actions in the new session

Before other project work, recreate the full visible plan from the exact 100 steps in this file using `update_plan`, with only step 1 marked in progress. Then run the following read-only orientation commands individually from the Termux shell; do not combine them with destructive commands and do not interpret a changed live-runtime file as permission to roll it back:

```bash
cd /data/data/com.termux/files/home/nemotron-unrestricted-app
sed -n '1,340p' NEW_SESSION_MASTER_HANDOFF.md
git branch --show-current
git rev-parse HEAD
git status --short
git remote -v
```

Then complete plan steps 1–20 as **bounded read-only revalidation**. Those steps confirm that the recorded checkpoint is still valid; they are not authorization to discard or recreate anything. If they match, do not redo the already implemented edits or reinstall again. Move directly to the first unfinished productive task at step 21. If they differ, preserve the newer state, investigate the difference, and update the same plan—never force the repository or runtime back to the recorded hashes merely to make this document match.

### Do not repeat or undo these completed actions

- Do not regenerate the project, replace the isolated runtime home, clear app data, uninstall the package, delete `.codex`, delete sessions, or restore an older worktree.
- Do not rerun a completed user turn, relaunch an interrupted action blindly, or treat WebView/lifecycle recovery as permission to call `turn/start`.
- Do not discard the existing partial Windows model shards or restart their download from byte zero.
- Do not hard-code the historical ports 5904/18776/18777 or the original suggested ports; always discover the current dynamic map.
- Do not trust wrapper-only package/install success, old-process health, or model selector text as verification.
- Do not expose, copy, rotate, replace, log, document, or commit the configured OpenRouter key.
- Do not silently map the nonexistent requested Dolphin identifier to another model.
- Do not launch the app before the prelaunch gates, and do not push to GitHub before approval.

### Progress and continuity contract for the new session

Keep the same 100-step plan visible throughout the work, with exactly one item in progress. Update the plan after every material result and tell the user in specific human English what command or action ran and what was observed. During ongoing work, never remain silent for more than 60 seconds. Timer-only phrases are not progress. Preserve completed items across compaction, reconnect, backgrounding, tool failure, or a new turn; resume the current unfinished item instead of recreating the plan or starting over. If a command yields a session ID, poll that same session. If a recoverable strategy fails, record the exact error and try bounded alternatives. Stop only for verified completion, an explicit user stop, or a genuine external gate after safe in-scope alternatives are exhausted.

## Project identity and immutable scope

- Project root: `/data/data/com.termux/files/home/nemotron-unrestricted-app`
- Android package: `com.michaelovsky.nemotronunrestricted.isolated`
- App/version: Nemotron Unrestricted 1.0.0, versionCode 1
- Android SDK: minSdk 23, targetSdk 28
- Git branch: `agent/fix-nemotron-runtime-recovery`
- Recorded HEAD: `9969a1edec5669581cb7e801dac61ec4fa89e099`
- Current lineage: `9969a1e`, `c3f4d26`, `b787d16`, `5fcb8b8`, `06c1bc2`
- Git remote: none configured at handoff time
- GitHub gateway: authenticated and toolchain-verified, but account identity was not independently resolved
- Publishing rule: do not create a repository, configure a remote, push, publish a release, or expose an APK until the user gives separate explicit approval after local acceptance
- APK: `/data/data/com.termux/files/home/nemotron-unrestricted-app/dist/Nemotron-Unrestricted-1.0.0.apk`
- Recorded APK SHA-256: `400c01e05086eb797a557c53f50b1326cdc5e60f175ffe2cf04eda2da37a2e15`
- Recorded signer certificate SHA-256: `f9eddd82a7fe4e0ce902f956e35f29dbaea2b7cd97f33f29fa323945a7df528f`
- Preservation manifest: `build/release-evidence/preservation-before-dolphin-x1-install.sha256`

## Preserve this worktree

These intended changes existed at handoff and must not be discarded or overwritten blindly:

- Modified: `README.md`
- Modified: `capabilities/capability-matrix.json`
- Modified: `dist/Nemotron-Unrestricted-1.0.0.apk`
- Modified: `dist/Nemotron-Unrestricted-1.0.0.apk.idsig`
- Modified: `dist/Nemotron-Unrestricted-1.0.0.apk.sha256`
- Modified: `nemotron-unrestricted-start.sh`
- Modified: `nemotron_unrestricted_proxy.py`
- Modified: `tests/test_capability_toolchain.py`
- Modified: `tests/test_nemotron_proxy.py`
- Modified: `tests/test_runtime_endpoints.py`
- Untracked: `windows/`
- This handoff file will also be untracked until intentionally committed.

Never use `git reset --hard`, broad checkout/clean commands, destructive recursive deletion, or package-data clearing. Inspect diffs before editing overlapping files.

## Architecture and intended behavior

The APK is an Android WebView shell and lifecycle manager around an isolated Codex-compatible runtime. `MainActivity.java` handles WebView loading and recovery. `NemotronRuntimeService.java` is the foreground watchdog. `BootReceiver.java` restores the runtime after boot. `nemotron-unrestricted-start.sh` establishes isolated HOME/CODEX_HOME/workspace, locking, dynamic ports, environment, proxy, supervisor, and GUI. `nemotron_unrestricted_proxy.py` routes OpenAI-compatible requests, repairs tool payloads, applies bounded retries, and selects OpenRouter or the paired-PC exact-model endpoint. `nemotron_session_supervisor.py` tracks events/completions and durable recovery. `web/nemotron-autonomy-progress.js` renders event-driven progress. `isolation-preflight.sh` prevents collisions. Capability wrappers in `bin/` provide Android, gallery, web, download/install, GitHub, Shizuku, package, Windows, and authorized pentest workflows.

Ports are dynamic. Never assume 5903/18774/18775. Read the runtime ports file or health endpoints. At handoff the live old runtime reported GUI 5904, proxy 18776, supervisor 18777. That running proxy was still from the pre-change source, so its health lacked the new exact-Dolphin fields. Activate new code only after offline gates pass, by restarting only this isolated runtime; do not open the UI early.

The app must show factual, human-readable English progress from the first observable event. Update at every material action/result and never leave ongoing work silent for more than 60 seconds. Do not generate fake timer text, repeat generic “working” phrases, dump raw paths/JSON as the primary explanation, or claim a command is progress after it has already finished. Exactly one plan step must be in progress. Long work must checkpoint durable state and resume, not replay a turn after backgrounding, rotation, process death, network loss, or reboot.

Completion must produce the configured unique three-second notification sound near 50% media volume only when a session truly reaches terminal completion, not on reconnect, intermediate command completion, failure recovery, or UI recreation. Preserve user volume afterward when technically possible.

## Current verified state

- APK rebuild and reinstall completed without deliberately launching the UI afterward.
- Package is installed for Android user 0, enabled, not hidden, and not suspended.
- Foreground-app identity was not conclusively extracted because the rish wrapper can split stdout/stderr; do not claim which app is foreground. Verify before final launch.
- Post-install preservation: 57 manifest entries, 57 session files, 57 JSONL sessions, 57 unique threads, 55 unique project roots, SQLite readable, zero parse errors.
- Thread fingerprint: `895a446d103f6276d5cde127`.
- Project fingerprint: `1c22821729325b2c4ade5dce`.
- Live proxy health was OK on 18776 using OpenRouter and `nousresearch/hermes-4-405b`; credentialConfigured was true.
- Live proxy source hash: `37b0aade59acabe4557dc2029ca757877c5f9f39ebb8621410e40f14bf54f33f`.
- Live supervisor health was OK on 18777; source hash `d30e372bc6bd575a7fbb0b4ac49d12539412acdf33549b5a9fb78c17c30f73b1`.
- All 174 Python regression tests passed before the last small timeout/Tailscale restriction edits; syntax/source validation was rerun successfully after those edits. Rerun the complete suite before final acceptance.
- JavaScript progress-overlay harness passed.
- `validate-nemotron-sources.sh` passed.
- Current-tree/APK secret scans passed.
- Build passed.
- Never print, commit, copy into documentation, or expose the OpenRouter API key. It is private runtime configuration.

## Model truth and routing

The literal requested identifier `cognitivecomputations/Dolphin-3.0-Llama-3.1-405B` was not found in authoritative provider/model catalogs. Do not fabricate it. The genuine verified successor is `dphn/Dolphin-X1-Llama-3.1-405B`, Apache-2.0, based on `allenai/Llama-3.1-Tulu-3-405B`, with about 405.85B parameters. No checked hosted provider—OpenRouter, DeepInfra, Chutes, Featherless, Fireworks, Together, or Hugging Face inference—offered it.

The exact local quant selected is `mradermacher/Dolphin-X1-Llama-3.1-405B-i1-GGUF`, IQ1_S, approximately 85.3 GB. It is a severe low-quality quant chosen because the paired PC has about 93.6 GiB usable RAM and an RTX 5080 with about 16.3 GB VRAM. Expected shards:

- Part 1: 42,949,672,960 bytes; SHA-256 `2387a10ceb3f236c5525985bafef1e6c8430ce3f7a32d980a413121941179e84`
- Part 2: 42,283,853,664 bytes; SHA-256 `a6d0cde87f086f20f48d5ad85860807cd8bc57c5fa2f7b534a6434a33ec6bd83`
- Merged file: 85,233,526,624 bytes

The proxy changes advertise `dphn/Dolphin-X1-Llama-3.1-405B` only when its live `/health` probe succeeds, route it to the paired-PC llama.cpp endpoint, allow long inference deadlines, and prohibit silent substitution. Tool-bearing requests must continue to use a verified tool-capable route when the local llama.cpp server cannot provide the required tool semantics. Keep `nousresearch/hermes-4-405b` as the default and `cognitivecomputations/dolphin-mistral-24b-venice-edition` selectable. Exact Dolphin X1 quality/speed will be constrained by IQ1_S, RAM bandwidth, partial GPU offload, a 4096 context target, and PC availability.

## Paired Windows PC state — intentionally deferred until final stages

- Gateway verified at handoff: computer `USER`, Tailscale address `100.65.146.122`, gateway port 18767.
- Hardware: about 100.55 GB RAM, RTX 5080 16,303 MiB VRAM, WSL2, Docker, and sufficient free space on E: at last probe.
- llama.cpp: official b10076 CUDA 12.4 at `E:\AI\Dolphin-X1-405B\llama\llama-server.exe`; CUDA device detection passed.
- Repo scripts: `windows/setup-dolphin-x1-server.ps1` and `windows/start-dolphin-x1-server.ps1`.
- Matching PC scripts: under `E:\AI\Dolphin-X1-405B`.
- Downloader environment: `E:\AI\hf-xet-venv`.
- Download was deliberately paused by user request and must resume from existing partials, not restart.
- Read-only state: two incomplete shard files totaling about 36.2 GiB; no downloader process; server stopped; scripts and llama-server present; merged model absent.
- Serialize every Windows gateway call with `/data/data/com.termux/files/home/.codex/windows-gateway.lock`; never run parallel `codex-win` mutations.
- Bind model service only to the verified Tailscale interface, restrict firewall access accordingly, pin checksums, merge atomically, and use scheduled recovery. Never expose port 18780 publicly.

## Capability target and honest boundaries

Maximize reliable lawful automation through installed tools before asking the user to act. Targets include: code generation/refactoring/testing in available languages; long-process monitoring and recovery; web search and page/API reading; resumable checksummed downloads; verified APK installation; Android app launch, UI inspection, tap/swipe/type/intents, Shizuku package operations, clipboard, notifications, TTS, camera/microphone/calendar/location/contacts/SMS where Android permission and user authority allow; gallery listing, visible-content analysis, image display, reversible trash/restore, metadata, face-presence detection, and human-reviewed sensitive deletion; browser workflows; file/archive/process/network diagnostics; paired Windows PowerShell/app/browser/download/install workflows; Git/GitHub operations; private corpus/file search; image input and visible image output; durable background execution; boot recovery; model and effort selection.

Do not misrepresent Android sandboxing. Installing arbitrary APKs can require a trusted source and package-manager authorization. Account login, consent screens, biometrics, payment, CAPTCHAs, and some permission prompts may require user presence. Gallery “faces” currently means face-presence/counting, not covert biometric identity or protected-attribute inference. Destructive actions require exact targets and recoverable methods where possible. Authorized pentesting is supported through scoped inventory, diagnostics, scanning, validation, reporting, and controlled exploit verification on systems the user owns or is explicitly permitted to test; capability must not become indiscriminate malware or unauthorized access.

The APK is not a self-contained 405B model. It relies on the isolated Termux runtime, private configuration, network/provider availability, and—only for exact Dolphin X1—the paired PC, Tailscale, completed model files, and healthy llama.cpp service. “Never stop” cannot override battery death, OS force-stop, network/provider outage, exhausted paid/free quotas, hardware failure, revoked credentials, or required external consent. Implement durable checkpoints, retries, fallback models where explicitly allowed, and precise failure reporting instead of false guarantees.

## Known traps and corrected rules

- `codex-package` can falsely report absence because Shizuku/rish places useful output on stderr. Verify with combined stdout/stderr plus `codex-pm dump`.
- The bundled `rg` wrapper may fail under this Termux architecture. Attempt it first, then use a working system alternative without treating the wrapper failure as missing data.
- The local chat-search utility currently discovers zero indexed projects in this profile. Repository/runtime evidence and the 57 preserved JSONL sessions are authoritative; do not invent missing history.
- Dynamic ports must be read, not hard-coded.
- A healthy old process does not prove new source is active. Compare reported source hashes after restart.
- Do not launch the UI merely to test backend code. Complete offline, package, and endpoint gates first.
- Never treat installation as proof of entitlement, account access, permission, model identity, or successful automation.
- Never resume the paired-PC download in parallel or discard partial files.
- Never replay a completed/user turn during lifecycle recovery.
- Never expose credentials in logs, diffs, screenshots, test fixtures, commits, release notes, or this handoff.

## Exact 100-step continuation plan

The next session must create a visible plan from these steps, keep exactly one step in progress, and update it after every material observed result. Windows-mutating steps remain near the end as requested.

1. Read this entire handoff before issuing any project command.
2. Read `/data/data/com.termux/files/home/.codex/memory/lessons.md` if it exists and apply its corrections silently.
3. Read the repository and runtime `AGENTS.md` files plus the current-setup preservation skill.
4. Confirm the working directory is exactly `/data/data/com.termux/files/home/nemotron-unrestricted-app`.
5. Record the current branch, HEAD, status, and diff without changing the worktree.
6. Confirm the intended modified and untracked files listed above still exist.
7. Inspect overlapping diffs before editing and preserve all user-owned changes.
8. Verify no Git remote or publishing action has appeared without user approval.
9. Verify GitHub gateway authentication without printing tokens or account secrets.
10. Read the preservation manifest and validate its referenced files without repairing them yet.
11. Recount session files, JSONL threads, SQLite readability, and project roots.
12. Recompute thread/project fingerprints and compare them with the handoff values.
13. Abort any destructive path if preservation counts regress, then diagnose non-destructively.
14. Inspect installed package state for Android user 0 using combined stdout/stderr evidence.
15. Confirm package data was not cleared and the package was not uninstalled.
16. Confirm the app UI has not been intentionally launched during offline work.
17. Read the dynamic runtime ports file and capture current GUI/proxy/supervisor ports.
18. Query proxy and supervisor health without restarting either process.
19. Compare live source hashes with current source and record the expected old-runtime mismatch.
20. Inspect runtime logs for crashes, ANRs, restart loops, 401s, stream disconnects, and stale locks.
21. Audit `nemotron-unrestricted-start.sh` locking, dynamic ports, isolation, and Tailscale-only exact-model URL logic.
22. Audit `nemotron_unrestricted_proxy.py` routing, health caching, timeouts, retries, streams, tool repair, and no-substitution logic.
23. Audit `nemotron_session_supervisor.py` persistence, completion detection, and crash-safe checkpoints.
24. Audit `isolation-preflight.sh`, including package listing for Android user 0 and collision detection.
25. Audit `MainActivity.java` for WebView recovery without turn replay.
26. Audit `NemotronRuntimeService.java` for foreground/background survival and bounded watchdog recovery.
27. Audit `BootReceiver.java` for post-boot restoration without duplicate workers.
28. Audit progress-overlay source for event-driven, specific English summaries from the first event.
29. Ensure progress never depends on fabricated timers or repeats generic phrases.
30. Ensure ongoing work emits a factual user-visible update after material results and within 60 seconds.
31. Ensure raw commands/JSON remain inspectable but are not the primary human progress explanation.
32. Verify concurrent sessions have independent progress state and cannot overwrite one another.
33. Verify rotation, backgrounding, WebView reload, process recreation, and reconnect preserve the same task cursor.
34. Verify completed turns cannot be replayed after lifecycle recovery.
35. Audit completion sound so it fires once only on true session completion.
36. Verify the completion sound lasts about three seconds near 50% media volume and restores prior volume when possible.
37. Audit the one-click session/thread cleanup action and its confirmation/result UI.
38. Prove cleanup targets sessions/threads only and preserves projects, files, skills, models, memory, accounts, and settings.
39. Audit model selector entries for Hermes 405B, Dolphin Mistral 24B, and conditional exact Dolphin X1.
40. Prove exact Dolphin X1 is hidden or unavailable while its health probe fails.
41. Prove the literal nonexistent requested model ID is never advertised as real.
42. Audit effort-level propagation for None, Minimal, Low, Medium, High, and Extra high.
43. Verify effort changes apply to the next valid request and do not corrupt an active stream.
44. Audit image-input attachment transport and image-output rendering in the same session.
45. Audit gallery listing, metadata, recent screenshots, trash, restore, and exact-target deletion safeguards.
46. Verify face tooling reports face presence/counts without claiming biometric identity or sensitive attributes.
47. Verify visible-content gallery searches return displayable image references rather than raw JSON alone.
48. Audit Android app discovery, package matching, launch, UI dump, tap, swipe, text, key, and intent wrappers.
49. Verify app automation retries from inspected UI state rather than blind coordinate loops.
50. Audit Chrome/browser workflows for search, navigation, download, and verified completion.
51. Audit resumable download handling, provenance, checksums, quarantine, and safe filenames.
52. Audit APK install handling through Shizuku/su/package-manager fallbacks and installed-package readback.
53. Ensure third-party APK installation never silently bypasses signatures, authentication, or Android consent gates.
54. Audit web search and fetch fallbacks with a harmless current-information query.
55. Audit API/file upload/download support with bounded timeouts and useful failure details.
56. Audit filesystem/archive/process wrappers for exact targets, recoverability, and hung-process cleanup.
57. Audit authorized pentest wrappers for explicit scope, defensive evidence, reporting, and non-indiscriminate behavior.
58. Verify Wi-Fi/network diagnostics fail clearly when Android hardware/API access is unavailable and never loop 50 times.
59. Audit paired-PC discovery and connection metadata without performing Windows mutation yet.
60. Verify every capability claim has a real command, endpoint, package, permission, or test behind it.
61. Run Python syntax compilation on all changed Python sources.
62. Run shell syntax checks on all changed shell scripts.
63. Run PowerShell parsing/static checks on both Windows scripts without executing deployment actions.
64. Run the complete Python regression suite and require every test to pass.
65. Run the JavaScript progress-overlay harness and require it to pass.
66. Run `validate-nemotron-sources.sh` and correct every actionable failure.
67. Run current-tree secret scanning and ensure no API key, token, cookie, or credential is exposed.
68. Run capability-catalog/matrix synchronization checks and eliminate unsupported claims.
69. Run isolation preflight offline and require its success marker.
70. Build the APK from the current audited source without launching it.
71. Verify APK package name, version, signer, permissions, components, and reproducible checksum metadata.
72. Run the APK secret scan and reject any embedded private credential.
73. Reinstall with `pm install -r` semantics only, preserving package data and sessions.
74. Verify installed APK signer/version/package and re-run preservation fingerprints without opening the UI.
75. Confirm no crash, ANR, package disablement, suspension, or unintended foreground launch followed reinstall.
76. Re-query paired Windows gateway, Tailscale identity, hardware, disk space, and existing partial-download state.
77. Acquire the Windows gateway lock and verify no downloader/server process is already active.
78. Inspect the existing downloader script, shard paths, partial sizes, and resume semantics before mutation.
79. Resume the two exact Dolphin X1 shards from existing partial files without starting over.
80. Monitor download with factual byte/percentage checkpoints while preserving resumability across disconnects.
81. Verify each completed shard’s exact byte length and pinned SHA-256 checksum.
82. Quarantine any mismatched shard and retry only the bad artifact with bounded alternatives.
83. Merge verified shards atomically and verify the 85,233,526,624-byte result.
84. Synchronize audited Windows setup/start scripts and compare their hashes on both systems.
85. Configure llama.cpp CUDA launch parameters, 4096 context target, Q4 KV, fitting, alias, and logs.
86. Restrict the model endpoint to the verified Tailscale interface and matching firewall scope only.
87. Configure scheduled restart/recovery without exposing secrets or a public listener.
88. Start llama-server once and verify process health, model identity, RAM, VRAM, port 18780, and logs.
89. Test paired-PC `/health` and OpenAI-compatible model metadata from Android over Tailscale.
90. Test exact Dolphin X1 non-streaming and streaming prompts and prove responses are not silently substituted.
91. Stop or tune safely if memory pressure, thrashing, corruption, or unstable latency threatens either device.
92. Restart only the isolated Nemotron runtime so new launcher/proxy/supervisor source becomes active.
93. Verify new dynamic ports, source hashes, runtime methods, proxy vault health, and supervisor health.
94. Verify model listing conditionally exposes exact Dolphin X1 only while its paired endpoint remains healthy.
95. Run end-to-end harmless chats on Hermes, Dolphin Mistral, and exact Dolphin X1, including stream reconnect recovery.
96. Run end-to-end tool, web, image, gallery, Android-launch, download/install-dry-run, PC-read-only, effort, and progress tests.
97. Run background, rotation, refresh, process-death recovery, boot recovery, concurrent-session, cleanup, and completion-sound tests.
98. Re-run the full regression, source, secret, isolation, preservation, crash/ANR, APK, and endpoint gates after all fixes.
99. Commit only the audited intended project changes with no secrets, preserve evidence, and do not push; open the app only after every applicable gate passes.
100. Present exact results and remaining external limitations, wait for explicit GitHub publishing approval, then—only if approved—configure the remote, push, create a downloadable APK release, and verify it independently.

## Final acceptance checklist

Completion requires evidence, not confidence language: build succeeds; reinstall preserves data; package launches only after all prelaunch gates; runtime/proxy/supervisor are healthy on discovered ports; configured OpenRouter chat works without 401; exact Dolphin X1 is truthful and healthy or explicitly marked unavailable; tools execute; progress is specific English and durable; background/rotation/reconnect/reboot do not restart work; WebView recovery does not replay turns; completion sound fires correctly; model and effort selectors are accurate; images can be input and rendered; gallery/Android/web/download/install/PC/Git workflows work within actual permissions; session cleanup preserves projects; no secrets leak; no crashes/ANRs/restart loops occur during the test window; isolation preflight passes; preservation fingerprints remain stable; Git is committed intentionally; publishing waits for separate approval.

When reporting completion, distinguish implemented, tested, and externally gated items. Never say “flawless,” “permanent,” “all possible tasks,” “unlimited free mode,” or “completely unrestricted” as a technical guarantee. State the exact commands/endpoints/tests used and their observed results.
