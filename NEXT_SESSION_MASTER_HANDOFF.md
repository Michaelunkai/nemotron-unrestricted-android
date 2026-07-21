# Nemotron Unrestricted — authoritative successor-session handoff

## Authority, project path, and how to use this file

This is the current continuation contract for:

`/data/data/com.termux/files/home/nemotron-unrestricted-app`

It supersedes `NEW_SESSION_MASTER_HANDOFF.md`, which is retained as historical evidence of the earlier checkpoint. Read this file completely before changing source, processes, packages, Windows state, Git state, or user data. The latest user message remains the primary mission. This handoff supplies full context and safety constraints; it is not permission to ignore a newer mission, replay completed work, publish anything, or perform destructive operations.

At the start of a new session:

1. Read this entire file and `/data/data/com.termux/files/home/.codex/memory/lessons.md`.
2. Read the applicable `AGENTS.md` and the `michNvidiaApp Current Setup` preservation skill.
3. Create the exact visible 100-step plan near the end of this file with `update_plan`, step 1 in progress and all other steps pending.
4. Update that same plan after every material command/result, keeping exactly one step in progress.
5. Complete read-only revalidation before mutation. Preserve newer valid state rather than forcing it back to the snapshot recorded here.
6. Merge the newest user mission into steps 31–75. If there is no newer mission, the only unfinished prior mission is the approval-gated publication decision described below.

Do not stop merely because work is long or a first strategy fails. Use bounded alternatives, preserve progress, and continue until the applicable mission and verification gates are complete, the user explicitly stops, or a real external authorization/platform/hardware gate remains. A 100-step plan is a visibility and continuity contract, not authorization to bypass safety, consent, credentials, Android protections, provider limits, or the GitHub publication gate.

## Exact resume checkpoint

Snapshot verified on 2026-07-21 after the prior implementation mission completed:

- Original 100-step implementation mission: steps 1–99 are complete and locally verified.
- Original step 100 is the only unfinished prior step: present exact results and external limitations, then wait for explicit GitHub publishing approval. Only after approval may a remote be configured, a repository/release created, the branch pushed, and the APK uploaded and independently verified.
- No Git remote is configured. Nothing has been pushed or released.
- GitHub tooling is authenticated and gateway-verified, but authentication is not publication authorization.
- The current source, APK, installed package, isolated runtime, and exact Dolphin X1 paired-PC route are complete and operating.
- The final Android app was launched and verified in the previous session. Do not open or foreground it merely for orientation. Reopen only when a new mission needs UI validation and the device is not actively being used by the user.
- The successor handoff itself is intentionally created after commit `cdb3552`; until separately committed, `git status --short` should show only `?? NEXT_SESSION_MASTER_HANDOFF.md`. Preserve it.

If a new user mission accompanies this handoff, perform that mission on top of the verified baseline. Do not rerun the completed 85 GB model download, rebuild/reinstall without a reason, replay old turns, or restart healthy services just to make progress counters move.

## Project purpose and honest scope

Nemotron Unrestricted is an Android AI-agent application built as an isolated Codex-compatible runtime and WebView shell. Its goal is reliable, tool-first autonomy for lawful user-authorized work: coding, research, web/API access, verified downloads and APK installation, Android UI/app automation, gallery operations, Git/GitHub work, durable long-running tasks, multimodal input/output, paired-Windows-PC work, and authorized defensive security testing.

“Unrestricted” means the app should avoid arbitrary app-added refusals, fake progress, generic capability disclaimers, unnecessary manual handoffs, and silent model substitution when an installed tool can lawfully perform the action. It does not authorize malware, credential theft, unauthorized intrusion, covert surveillance, CAPTCHA/authentication bypass, destructive attacks, protected-attribute inference, or actions outside the user's authority. Provider policy, Android security, account authentication, quotas, physical presence, hardware limits, and network availability remain real boundaries and must be reported honestly.

The APK is not a self-contained 405B model. It uses the isolated Termux runtime, private provider configuration, and the paired Windows PC over Tailscale for exact Dolphin X1.

## Repository and release identity

- Project root: `/data/data/com.termux/files/home/nemotron-unrestricted-app`
- Git branch: `agent/fix-nemotron-runtime-recovery`
- Verified HEAD: `cdb35520bd61f29687d5d73a1f585d9076c0af9d`
- Commit subject: `Complete Nemotron autonomy and Dolphin X1 recovery`
- Commit timestamp: `2026-07-21T23:15:02+03:00`
- Worktree immediately before this handoff: clean.
- Expected worktree immediately after this handoff: only this new file untracked unless a later session has valid newer changes.
- Authorized public repository: `https://github.com/Michaelunkai/nemotron-unrestricted-android`.
- Repository discovery rejected the similarly named `Michaelunkai/nemotron-unbound-android` because it is a different package (`com.michaelovsky.nemotron.unbound`), provider architecture, signer, and APK.
- Publication was explicitly authorized by the user on 2026-07-21. The repository was created public so anyone can access the source and release APK.
- GitHub tooling: `./bin/codex-github status` returned authenticated, gatewayVerified, ghAvailable, gitAvailable, ok, and verified all true. Never print or document tokens.
- Publishing gate: satisfied for `Michaelunkai/nemotron-unrestricted-android` by the user's explicit instruction. Do not redirect future pushes/releases to a different repository without new authorization.
- Android package: `com.michaelovsky.nemotronunrestricted.isolated`
- App/version: Nemotron Unrestricted 1.0.0, versionCode 1
- Android SDK: minSdk 23, targetSdk 28
- Final APK: `/data/data/com.termux/files/home/nemotron-unrestricted-app/dist/Nemotron-Unrestricted-1.0.0.apk`
- APK size: 42,160 bytes
- APK SHA-256: `c604f0b456428b9fdf3bb62917789b07d5f3e44e9f5c6772581d20b96cdf0385`
- APK idsig SHA-256: `c87652a38918427ef546b69a4776d982504500745f840127880a83c20ebc0af7`
- Signer certificate SHA-256: `f9eddd82a7fe4e0ce902f956e35f29dbaea2b7cd97f33f29fa323945a7df528f`
- APK signatures: v1, v2, and v3 verified true.

## Architecture and important files

- `android/app/src/main/java/com/michaelovsky/nemotronunrestricted/MainActivity.java`: WebView host, lifecycle handling, and recovery without turn replay.
- `android/app/src/main/java/com/michaelovsky/nemotronunrestricted/NemotronRuntimeService.java`: foreground watchdog and bounded runtime recovery.
- `android/app/src/main/java/com/michaelovsky/nemotronunrestricted/BootReceiver.java`: boot/package-replacement restoration without duplicate work.
- `nemotron-unrestricted-start.sh`: isolated HOME/CODEX_HOME/workspace, locks, dynamic port allocation, process ownership, environment, GUI, proxy, and supervisor startup.
- `nemotron_unrestricted_proxy.py`: OpenAI-compatible routing, provider/model truth, request normalization, tool-call repair, retries, streaming, exact-Dolphin health gating, and no-substitution enforcement.
- `nemotron_session_supervisor.py`: durable events, active-turn/completion tracking, notifications, and recovery state.
- `web/nemotron-autonomy-progress.js`: event-driven human-readable progress overlay.
- `isolation-preflight.sh`: collision and isolation validation.
- `verify-nemotron-preservation.sh`: credential-free manifest and session-state verifier.
- `validate-nemotron-sources.sh`: source/catalog consistency gate.
- `bin/`: capability wrappers for Android, Shizuku, packages, gallery, web, download/install, GitHub, Windows, and scoped defensive workflows.
- `windows/setup-dolphin-x1-server.ps1`: paired-PC installation/firewall/scheduled-task setup.
- `windows/start-dolphin-x1-server.ps1`: exact-model llama.cpp startup wrapper.
- `tests/`: Python and JS regression/acceptance coverage.
- `build/release-evidence/`: preservation and release evidence.
- `dist/`: final signed APK and checksum sidecars.

## Protected state and non-destructive rules

Preserve all user projects, conversations, memories, credentials, runtime data, package data, and intentional changes. Never run `git reset --hard`, broad `git checkout`, `git clean`, recursive deletion against a broad/unresolved path, package uninstall, `pm clear`, `.codex` deletion/replacement, session deletion, or app-data clearing. Do not kill sibling app servers or other isolated apps.

Preservation baseline:

- Manifest: `build/release-evidence/preservation-before-dolphin-x1-install.sha256`
- Last stable manifest verification: 57 entries, 57 session files, 57 JSONL files, 57 unique threads, 55 unique project roots, SQLite readable, zero parse errors.
- Stable thread fingerprint: `895a446d103f6276d5cde127`
- Stable project fingerprint: `1c22821729325b2c4ade5dce`
- During creation of this handoff, the static checksum manifest differed only at the active current-session JSONL because Codex was legitimately appending to it.
- Live structural readback then showed 59 session files, 59 JSONL files, 59 unique threads, 57 unique project roots, and zero parse errors. Increased counts and a changed fingerprint are expected from new sessions; regression, disappearance, unreadable SQLite, or parse errors require non-destructive investigation.

Never “repair” an active session file back to an older checksum. For future verification, first identify exactly which manifest entries changed. Active/new session JSONL growth is legitimate; missing files, truncated history, decreased counts, changed old immutable files, or parse errors are not.

Secrets must remain private. Never print, copy, commit, screenshot, embed in APK/docs/tests, rotate, or replace the configured OpenRouter key or any GitHub/gateway credential. Credential presence may be verified only through boolean/fingerprint evidence that reveals no value.

## Android installed-package state

- Installed for Android user 0: true.
- Version: 1.0.0, versionCode 1.
- minSdk 23, targetSdk 28.
- Enabled, not hidden, not suspended, not quarantined.
- Package data existed at the last check; first install time remained 2026-07-20 and update time was 2026-07-21 23:13:45 +03:00.
- Runtime permissions included notifications, Termux RUN_COMMAND, camera, and microphone as previously granted.
- Installed package/signature and final APK were independently read back during acceptance; do not trust installer-wrapper success alone.
- If reinstall is genuinely required, preserve data with replacement semantics, stream exact bytes through `pm install -r -S` or stage under a verified `/data/local/tmp` path when Android cannot read Termux/FUSE paths, then compare installed `base.apk`, version, signer, and package identity.
- Android UI dumps can be stale or belong to another foreground app. Verify `topResumedActivity`/current package and the dump root before interpreting screenshots or XML. The user may be using the phone; avoid stealing foreground unnecessarily.

## Active isolated runtime state

Ports are dynamic and must be read from `runtime/.codex/supervisor/ports.env`, never assumed. At this snapshot:

- GUI: 5904
- proxy: 18774
- supervisor: 18775
- Proxy process at the completed restart: PID/PGID 24724; supervisor PID/PGID 24701; GUI session leader PGID 24735. These PIDs are historical and must be re-queried.
- Proxy `/vault-health`: HTTP 200, exactDolphinAvailable true, exact model `dphn/Dolphin-X1-Llama-3.1-405B`, exact provider `paired-pc-llama.cpp`, `modelSubstitution:false`.
- Proxy source hash: `023d78b58409d992f397657e058c11b082cebef788604ed7087cb5c98d30e04d`
- Supervisor `/health`: HTTP 200, activeTurnCount 0 at snapshot.
- Supervisor source hash: `d30e372bc6bd575a7fbb0b4ac49d12539412acdf33549b5a9fb78c17c30f73b1`
- Runtime methods verified include config/read, thread/start, turn/start, turn/interrupt, and thread/delete.

Ordinary launcher use must reuse a healthy owned runtime. An explicit restart is allowed only after verifying exact process ownership, zero active turns, and the correct session leaders. Kill only owned process groups. Never use broad name matching that can kill sibling services.

Lifecycle recovery must never create a replacement turn, replay a completed turn, or blindly interrupt. It may persist state, reconnect streams, rehydrate the exact thread/turn, and reconcile authoritative status. Progress must be specific, event-driven English from the first observable action, updated after material results and within 60 seconds during long work; timer-generated generic text is not progress. The completion sound fires once only at genuine terminal completion.

## Model truth and routing

- Default hosted model: `nousresearch/hermes-4-405b`.
- Selectable alternate: `cognitivecomputations/dolphin-mistral-24b-venice-edition`.
- Exact paired-PC model: `dphn/Dolphin-X1-Llama-3.1-405B`.
- The originally requested literal identifier `cognitivecomputations/Dolphin-3.0-Llama-3.1-405B` does not exist in checked authoritative catalogs and must never be advertised or silently mapped to another model.
- Exact Dolphin X1 is advertised only while its live health probe succeeds. Requested and effective model identity must remain truthful, with `modelSubstitution:false`.
- Tool-bearing requests must use a route that actually supports the required tool semantics; after the first tool result, return tool choice to auto to avoid loops.
- Reject pseudo tool calls unless they match an advertised, schema-valid tool. Protocol debris such as a lone `</tool_call>` is a recoverable provider failure, not completion.

Exact Dolphin X1 details:

- Model parameters: 405,853,651,008.
- Quantization: IQ1_S, a severe low-bit compromise required by available hardware.
- Runtime context: 4096; training context metadata: 131072.
- Merged GGUF: `E:\AI\Dolphin-X1-405B\Dolphin-X1-Llama-3.1-405B.i1-IQ1_S.gguf`
- Merged size: 85,233,526,624 bytes.
- Part 1 size/hash: 42,949,672,960 / `2387a10ceb3f236c5525985bafef1e6c8430ce3f7a32d980a413121941179e84`
- Part 2 size/hash: 42,283,853,664 / `a6d0cde87f086f20f48d5ad85860807cd8bc57c5fa2f7b534a6434a33ec6bd83`
- Paired endpoint: `http://100.65.146.122:18780`
- Snapshot live checks: `/health` HTTP 200 and `/v1/models` HTTP 200 with the exact alias, 405,853,651,008 parameters, IQ1_S, and context 4096.
- Measured minimal exact-model latency is slow because of 405B partial offload: direct non-streaming about 588 s, direct streaming about 260 s, and proxy non-streaming about 309 s. This is a real external limitation, not a hang by itself.

## Paired Windows PC state

- Computer: `USER`; gateway user `user`.
- Tailscale address: `100.65.146.122`.
- Windows gateway port: 18767; elevated status true.
- `codex-win {"action":"status"}` returned the expected gateway/companion markers. Its outer status may say `completed_unverified`; state-changing actions remain fail-closed and require independent readback.
- Hardware: about 100.55 GB RAM and NVIDIA RTX 5080 with 16,303 MiB VRAM.
- llama.cpp: `E:\AI\Dolphin-X1-405B\llama\llama-server.exe`.
- Scheduled task: `Nemotron-Dolphin-X1-405B`, enabled/running at last acceptance, logon trigger, restart count 999, two-minute restart interval, unlimited execution, IgnoreNew.
- Server arguments include exact alias, Tailscale host, port 18780, context 4096, parallel 1, threads 8, batch 128, ubatch 64, fit enabled, fit target 2048, Q4_0 K/V, flash attention, Jinja, metrics, and no Web UI.
- Firewall rule: `Nemotron Dolphin X1 405B (Tailscale only)`, inbound allow TCP 18780, local `100.65.146.122/32`, remote `100.64.0.0/10`, all profiles. Never expose it publicly.
- Remote setup-script hash: `2bea45c160af798e34875890240f3d1b71760b53b8863b82fc89a6f1c9864018`.
- Remote start-script hash: `5f207eee2dd0de8d3f129b813a6da132c84e7516480a9fb9a78bb47e02db4202`.
- Last healthy resource evidence was about 15,488 MiB VRAM used and about 40.27 GB free RAM. Re-query instead of hard-coding process IDs or resource values.
- Serialize Windows gateway operations with `/data/data/com.termux/files/home/.codex/windows-gateway.lock`. Never run parallel Windows mutations.

## Completed acceptance evidence

- Full Python regression suite: 174/174 passed.
- Lifecycle-focused suite: 62/62 passed.
- Broad acceptance-focused suite: 82/82 passed.
- Source validator: Python 29, shell 27, JavaScript 2, and progress-overlay harness passed.
- JavaScript progress-overlay harness passed after changing the human checkpoint from 90 seconds to 55 seconds and synchronizing the vendor asset/test.
- Current-tree/history/APK secret scans passed: worktree 94 files, history 0 findings, APK 15 entries checked.
- Isolation preflight passed.
- APK build, package/version/signer/signature checks, and data-preserving installation passed.
- No Android crash or ANR was found.
- Exact-model health gating and listing tests passed.
- Installed runtime endpoints returned HTTP 200.
- Harmless chat tests passed on Hermes, Dolphin Mistral, and exact Dolphin X1. Exact responses reported the exact model and returned `OK` without substitution.
- Hermes proxy chat completed in about 0.542 s; Dolphin Mistral in about 15.206 s; Hermes stream reconnect completed in about 0.28 s with three events and DONE.

These are accepted baseline results. Re-run only the gates proportional to a new change. A documentation-only read does not justify rebuilding/reinstalling or rerunning the 405B download.

## Known failures and corrected operating rules

1. A system `rg` binary may fail with `cannot execute: required file not found`. Use the working launcher/project path or bounded `find`/`grep`; do not claim files are absent.
2. `codex-github` may not be globally discoverable. Use `./bin/codex-github` from this project.
3. Direct `codex-fetch` can expose compressed bytes on some sites; use a normalized/Jina fallback and verify content.
4. `codex-delete --help` may treat `--help` as a target. Never infer CLI behavior from that call and never target broad paths.
5. Hugging Face Xet relaunch truncated partial files. Use `HF_HUB_DISABLE_XET=1` for HTTP Range resume and verify byte monotonicity. The model is now complete; do not download it again.
6. Windows foreground hash/copy calls can hard-time-out near 300 seconds. Use one detached bounded worker, an atomic receipt, and poll it under the gateway lock.
7. PowerShell `Get-Content -Raw` serialized huge content poorly; use `[IO.File]::ReadAllText` for exact large text.
8. NetSecurity CIM cmdlets failed with `0x80041010 Invalid class`; the verified fallback is `netsh advfirewall` plus full verbose readback.
9. PowerShell `*>>` made the scheduled llama wrapper exit 1. Use `Start-Process -Wait` with separate stdout/stderr logs.
10. Stopping an 80+ GB llama process can take time. Wait until the exact old PID is absent before starting another instance.
11. Android dumps may be stale and from another app. Verify the resumed/root package before reading or presenting them.
12. The correct focused unittest class is `ProxyNormalizationTests`; full discovery is authoritative when selectors fail.
13. Isolation preflight can transiently fail its 1.5 s endpoint identity check. Verify the exact endpoint and permit one bounded rerun only.
14. A transient Wi-Fi regression passed isolated and on one bounded full-suite retry; never hide the initial result, but final full suite is green.
15. Package/install wrappers may report success without replacing bytes. Always verify package-manager version, signer, installed hash, data inode/preservation, and process state.
16. `pm install -r` may fail from Termux-private/FUSE paths. Use exact-byte stdin streaming or verified `/data/local/tmp` staging, then remove the staging copy.
17. A healthy old process does not prove edited source is active. Compare source hashes after an owned restart.
18. Never treat installation as proof of entitlement, authentication, permissions, model identity, or functional completion.
19. Do not fabricate availability for an absent model or substitute silently. Health, listing, response metadata, and requested/effective identity must all agree.
20. The user can change the foreground app within milliseconds. Reject mismatched screenshots and avoid fighting the user for focus.

## New mission routing and completion rules

The newest user instruction always determines productive work:

- If the user provides a new coding, testing, Android, model, or Windows mission with this file, inspect the verified baseline and implement that mission without replaying completed work.
- If the mission overlaps changed files, inspect diffs first and preserve user-owned edits.
- If the user asks only for status/explanation, stay read-only.
- If no mission is supplied, resume at the publication decision only: report that local acceptance is complete and request explicit approval plus the destination private GitHub repository. Do not publish by assumption.
- A user instruction to “continue,” “finish,” or “do not stop” requires persistence but does not authorize destructive actions, credentials exposure, public release, repository creation, payments, bypasses, or work outside the stated scope.
- Complete each applicable plan step. Conditional/no-op steps may be marked complete with exact evidence explaining why they did not require mutation.

## Exact fresh 100-step visible continuation plan

Create these exact 100 visible steps in the new session. Keep exactly one in progress. For a supplied new mission, replace only the bracketed mission details in steps 31–75 while retaining their safety/verification intent; do not reduce the plan below 100 steps.

1. Read this successor handoff completely before other project actions.
2. Read the accumulated launcher lessons and apply every relevant corrected rule.
3. Read applicable AGENTS instructions and the current-setup preservation contract.
4. Confirm the exact project root without changing it.
5. Create this exact 100-step visible plan with only step 1 initially in progress.
6. Record the newest user mission verbatim and distinguish it from historical work.
7. Confirm whether the mission is read-only, diagnostic, implementation, UI, Windows, or publishing work.
8. Identify any authority, external-state, destructive, credential, payment, or publication boundaries.
9. Record Git branch, HEAD, status, diff summary, and remotes read-only.
10. Preserve this handoff and all unexpected/newer user-owned worktree changes.
11. Confirm the recorded commit lineage still contains `cdb3552`.
12. Verify no remote, push, or release appeared without explicit approval.
13. Verify GitHub tool authentication without displaying credentials.
14. Inspect the preservation manifest and identify changed entries without restoring them.
15. Recount live sessions, JSONL files, threads, project roots, SQLite status, and parse errors.
16. Explain legitimate active-session growth separately from loss or corruption.
17. Verify the final APK and checksum sidecar still agree.
18. Verify APK package, version, signer, and signature schemes read-only.
19. Verify the installed Android package identity and preserved data state if relevant.
20. Read dynamic GUI, proxy, and supervisor ports from the runtime ports file.
21. Query proxy vault health and compare its source hash with the current source.
22. Query supervisor health and require zero active turns before any restart.
23. Verify exact Dolphin health gating and `modelSubstitution:false`.
24. Query the paired PC `/health` and `/v1/models` only if model state matters.
25. Verify Windows gateway identity and Tailscale scope only if Windows work matters.
26. Inspect current logs for errors directly relevant to the newest mission.
27. Map the mission to architecture files, tests, packages, processes, and endpoints.
28. Inspect all overlapping diffs before editing any file.
29. Establish bounded acceptance criteria that prove the requested outcome.
30. Tell the user the exact first productive action and observed baseline.
31. Inspect the primary source/configuration surface for the newest mission.
32. Inspect the first dependent component that consumes that surface.
33. Inspect the second dependent component that consumes that surface.
34. Inspect relevant persistence, lifecycle, or recovery behavior.
35. Inspect relevant UI/progress behavior and accessibility implications.
36. Inspect relevant model/provider/tool routing behavior.
37. Inspect relevant Android permission/package constraints.
38. Inspect relevant Windows/network constraints when applicable.
39. Inspect existing unit tests covering the requested behavior.
40. Inspect existing integration/acceptance tests covering the requested behavior.
41. Define the smallest safe implementation slice for the mission.
42. Implement the first source change with `apply_patch`.
43. Review the first change for accidental scope expansion.
44. Implement the next required source change with `apply_patch`.
45. Synchronize any duplicated/generated/vendor copy required by repository conventions.
46. Update capability/catalog metadata only for behavior backed by a real implementation.
47. Add or update a focused regression test for the first changed behavior.
48. Add or update a focused regression test for the second changed behavior.
49. Add lifecycle/recovery coverage when the mission can survive interruption.
50. Add model-truth/no-substitution coverage when routing is affected.
51. Add exact-target/destructive-safety coverage when files/packages/data are affected.
52. Run Python syntax checks on changed Python files.
53. Run shell syntax checks on changed shell files.
54. Run Java/Android compilation checks when Android sources changed.
55. Run PowerShell parse/static checks when Windows scripts changed.
56. Run JavaScript syntax or harness checks when Web UI/progress changed.
57. Run the narrowest focused test for the first change.
58. Fix any focused-test failure at its root cause.
59. Rerun the focused test and capture the exact pass result.
60. Run the next relevant focused test group.
61. Fix any second-order regression without discarding user changes.
62. Verify secrets and credentials were not added to source, logs, or fixtures.
63. Verify capability claims still match real commands/endpoints/permissions.
64. Verify lifecycle recovery cannot replay or duplicate side effects.
65. Verify progress is factual, event-driven, specific, and timely.
66. Verify model requested/effective identity remains truthful.
67. Verify dynamic ports and sibling-runtime isolation remain intact.
68. Verify destructive actions use exact targets and recoverable methods where possible.
69. Run the relevant broader Python regression suite.
70. Run the progress-overlay harness when UI/progress code is in scope.
71. Run `validate-nemotron-sources.sh` when source/catalog state changed.
72. Run isolation preflight when launcher/runtime/package state changed.
73. Review the complete diff for correctness and unrelated changes.
74. Reconcile documentation with the implemented and verified result.
75. Confirm every newest-mission acceptance criterion now has evidence.
76. Decide whether an APK rebuild is actually required by the changes.
77. If required, build the APK without launching the app.
78. If built, verify package, version, signer, permissions, components, and checksums.
79. If built, run current-tree/history/APK secret scans.
80. Decide whether data-preserving installation is required for end-to-end proof.
81. If required, capture preservation evidence immediately before installation.
82. If required, install with exact-byte replacement semantics and no data clear.
83. If installed, independently compare installed package/version/signer/APK hash.
84. If installed, verify session/project counts and data inode did not regress.
85. Decide whether an isolated-runtime restart is required by changed backend source.
86. If required, re-query exact owned process groups and active-turn count.
87. If safe and required, restart only the isolated Nemotron runtime.
88. Verify new dynamic ports, source hashes, proxy health, and supervisor health.
89. Decide whether paired-PC mutation is required; keep read-only if it is not.
90. If required and authorized, serialize Windows work under the gateway lock.
91. Verify exact Dolphin `/health`, `/v1/models`, firewall scope, task, logs, and resources.
92. Run harmless non-streaming and streaming model checks proportional to routing changes.
93. Verify no silent substitution and record real latency/external limitations.
94. Decide whether Android UI launch is required and safe while the user uses the device.
95. If required, launch once and verify current package before UI evidence.
96. Run the smallest end-to-end user flow proving the newest mission.
97. Recheck crashes, ANRs, endpoint errors, preservation, secrets, and worktree state.
98. Commit only intentional local changes if the mission includes or clearly requires a commit.
99. Present exact completed results, tests, artifacts, and remaining honest limitations.
100. If and only if explicit publishing approval plus a private destination exist, configure the remote, push, create/upload the APK release, independently download/hash it, and report the verified URL; otherwise stop at the publication gate with all local work preserved.

## Safe orientation commands

Run individually or in bounded read-only groups; never combine them with destructive actions:

```bash
cd /data/data/com.termux/files/home/nemotron-unrestricted-app
sed -n '1,520p' NEXT_SESSION_MASTER_HANDOFF.md
git branch --show-current
git rev-parse HEAD
git status --short
git remote -v
cat runtime/.codex/supervisor/ports.env
./bin/codex-github status
sha256sum dist/Nemotron-Unrestricted-1.0.0.apk
```

For preservation, do not treat a changed active JSONL checksum as automatic corruption. First list only failed manifest entries, then run structural counting and parse validation. For runtime health, source the live ports file and query the exact ports. For installed-package evidence, account for Shizuku/rish stdout/stderr wrapping and independently read back package-manager state.

## Final publication contract

Local implementation and acceptance are complete at this snapshot. Publication remains deliberately unperformed. A new session must not create a GitHub repository, configure a remote, push, make the code public, create a release, or upload the APK unless the user explicitly approves that action and identifies the destination. Prefer a private repository unless the user explicitly requests public visibility. After authorization, independently verify the pushed commit and download the release APK to compare its SHA-256 with `c604f0b456428b9fdf3bb62917789b07d5f3e44e9f5c6772581d20b96cdf0385` (or a newer intentionally rebuilt artifact documented by the new mission).

This handoff is context, safety policy, verified evidence, and a continuation map. It is not a reason to restart completed work. Continue from the newest user mission, or from the explicit publication gate if no newer mission exists.
