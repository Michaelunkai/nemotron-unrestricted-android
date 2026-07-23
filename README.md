# Nemotron Unrestricted for Android

The current release is v1.9.0/code 10 at `dist/Nemotron-Unrestricted-1.9.0.apk`, SHA-256 `edf81d2ce9a6caaf302b3872fd5f4d35d13e4fa0b4f8456eea7d64f7b8bdeb2f`. It preserves the completed UI/runtime recovery, exact model/effort switching, background watchdog, three-second completion sound, PC/network routes, and same-session verified image rendering while adding hash-verified large Android readbacks, decoded PNG/XML UI evidence, safer semantic exploration, Android 23–36 MediaStore compatibility, and offline English gallery OCR/search.

Release acceptance passed 384 path-independent automated tests, source validation, four off-device 945×2048 UI goldens, the progress and executable gallery-frontend harnesses, source and signed-APK secret scans, two byte-identical builds, and package/version/signature checks. Final public-download, in-place-install, state-preservation, live Android, private-WebView, gallery, background, and network proofs are recorded in `NEXT_SESSION_MASTER_HANDOFF.md`.

Nemotron Unrestricted is an independent Android launcher and Termux-hosted agent workspace for OpenRouter models. The local proxy adds no prompt/response content classifier; it provides OpenAI-compatible routing, bounded retries, tool-schema repair, and metadata-only auditing. Provider behavior, account access, Android permissions, target authorization, and hardware limits still apply.

## Download the Android APK

The public source repository is [Michaelunkai/nemotron-unrestricted-android](https://github.com/Michaelunkai/nemotron-unrestricted-android). The universal Android 1.9.0 APK is available from the [v1.9.0 release](https://github.com/Michaelunkai/nemotron-unrestricted-android/releases/tag/v1.9.0):

- [Download Nemotron-Unrestricted-1.9.0.apk](https://github.com/Michaelunkai/nemotron-unrestricted-android/releases/download/v1.9.0/Nemotron-Unrestricted-1.9.0.apk)
- SHA-256: `edf81d2ce9a6caaf302b3872fd5f4d35d13e4fa0b4f8456eea7d64f7b8bdeb2f`
- Signing certificate SHA-256: `f9eddd82a7fe4e0ce902f956e35f29dbaea2b7cd97f33f29fa323945a7df528f`

Android users can download and install the APK on compatible devices after allowing installation from their chosen browser/file manager. The APK is the launcher and lifecycle manager; full agent operation also requires the Termux-hosted repository/runtime, local credentials, permissions, and—only for exact Dolphin X1—the paired-PC setup described below. Installing the APK alone does not bundle an 85 GB model or bypass Android/provider requirements.

## Identity and architecture

- Android package: `com.michaelovsky.nemotronunrestricted.isolated`
- Activity: `.MainActivity`
- Version: 1.9.0 (`versionCode 10`)
- GUI: first free loopback port from 5903
- Proxy: first free loopback port from 18774
- Supervisor: first free loopback port from 18775
- Runtime root: `/data/data/com.termux/files/home/nemotron-unrestricted-app/runtime/.codex`

The APK is a native WebView launcher and foreground watchdog. The CodexApp web runtime, proxy, supervisor, sessions, memories, configuration, and tools run from this repository under Termux. The APK alone is therefore not a standalone model or a self-contained Termux distribution.

Each service proves its identity before reuse. Runtime ports are persisted in `runtime/.codex/supervisor/ports.env`; source hashes force a restart when proxy or supervisor code changes. The app checks the proxy identity and exact loopback origin before loading the GUI or granting WebView media access.

## Model routing

The default text model is `nousresearch/hermes-4-405b` with a configured 131,072-token context. The literal requested identifier `cognitivecomputations/Dolphin-3.0-Llama-3.1-405B` does not exist in the Hugging Face or provider catalogs. The verified 405-billion-parameter successor is `dphn/Dolphin-X1-Llama-3.1-405B` (Apache-2.0, based on `allenai/Llama-3.1-Tulu-3-405B`). It is served from the paired PC as an exact 85.3 GB IQ1_S GGUF through `llama.cpp`; the proxy advertises it only after a live health response and never silently substitutes a smaller model.

Tool-bearing requests continue to use a current zero-price catalog model that explicitly advertises tool support, while image requests require a current zero-price model advertising image input and text output. Availability, price, quotas, context, and provider behavior can change, so current claims are checked against the live catalog rather than treated as permanent.

## What is included

- Native WebView with exact-origin navigation/permission controls, token-bound JavaScript bridge, bounded visual-ready loading, file chooser, and renderer recovery.
- Sticky foreground runtime watchdog and boot/package-replaced receivers.
- Dynamic, loopback-only GUI/proxy/supervisor selection with ownership and source-hash checks.
- OpenRouter proxy with bounded concurrency/body/response sizes, retry deadlines, tool routing, and JSON/SSE tool-argument repair.
- Native English-first progress summaries scoped to the visible thread, with polite atomic live-status accessibility and exact commands/output retained only in expandable technical evidence.
- A factual supervisor heartbeat at most 105 seconds apart while a turn is active, derived only from the exact turn's next action or last verified progress and never from a generic timer message.
- Active model/effort changes persist the exact selection, stop the exact active provider call once, and require an explicit safe continuation; no tool, approval, mutation, or turn is replayed automatically.
- Durable metadata-only active/progress/completion ledgers with event deduplication, restart-safe global and per-turn sequencing, filtered readback, and rejection of foreign, regressing, late, or raw-command progress.
- Guarded Android package controls that refuse destructive actions against the original Codex app, Codex Frontier, the NVIDIA app, Termux, Shizuku, and Android system packages.
- Project-local Android, web, confined download, signer-pinned APK, Wi-Fi, LAN, and authorized diagnostic workflows. See `capabilities/CAPABILITY_CATALOG.md` for the exact command surface.
- Resumable gallery face-presence and non-sensitive visible-content scans with eight-image batches, omitted-receipt retries, exact offsets, versioned MediaStore-bound receipts, verified contact sheets, automatic same-session lazy previews, and tap-to-open full-size viewing. “All/every” requests continue until `hasMore:false`.
- Receipt-backed trip workspaces with bounded headless research, an itinerary, ICS calendar file, encoded Google Maps handoff, action plan, source metadata, hashes, and change-detecting verification.
- Resolvable Android map, navigation, waypoint, and calendar intents; semantic UI suggestions rank fresh visible labels/descriptions/resource IDs, exclude password fields, refuse ambiguous close ties, and require a postcondition before mutation.
- Read-only Android permission readiness reports that distinguish actual grants from capabilities that still require an installed companion, Shizuku route, account, or user-visible Android consent.
- Hash-verified staged Shizuku readbacks avoid truncating large package, MediaStore, and UI evidence; package permission reports are scoped to Android user 0 and retain fully qualified custom permissions.
- Android UI screenshots are decoded and dimension-checked as PNG, hierarchy dumps are parsed as XML, and bounded semantic exploration refreshes every snapshot, rejects ambiguous targets, and stops on package drift or repeated screens.
- MediaStore inventory adapts to Android 23–36 columns, prefers provider-returned confined paths, records generations/pending state where available, and supports resumable offline English OCR search with a private SQLite WAL cache and exact word/line evidence.
- Twelve dependency-aware scaffold templates including Python, Go, Rust, Java, Kotlin, C17, C++17, Node.js, dependency-free Node full-stack, web, PWA, and Android; toolchain and pipeline syntax checks cover the native additions.
- Receipt-backed deployment status, plan, and execution for already-authenticated Vercel, Cloudflare Pages, and Netlify CLIs, with an exact tree hash, noninteractive command, HTTPS readback, and truthful external-gate reporting when account authorization is absent.
- Structured generated-image outputs remain persisted and rendered through the native `imageView` path; a prose claim, filename alone, or inaccessible image URL is never treated as successful image output.
- Android route verification that falls back from restricted kernel routes to sanitized ConnectivityService metadata and a no-payload kernel socket route probe.
- Fail-closed read-only Windows PowerShell routing, a separate direct Git/GitHub route, and a structured receipt-backed cleanup workflow; caller-authored deletion and encoded/dynamic/nested shell invocation are rejected before the paired gateway.
- One shared SHA-256-identified capability contract for every selectable model, with tool-only continuation routing that preserves the transcript, instructions, attachments, approvals, plan, and factual English progress.
- Typed, independently verified task/command/schedule, PC route/monitor, research/browser, scaffold/toolchain/pipeline/release, Android intent/UI/device I/O, file/archive, secret/security, encrypted-care, and safe-mode/synchronization workflows.

## Requirements

- Android with Termux and Termux:API installed and authorized.
- Shizuku/rish for privileged Android inspection and guarded package operations.
- JDK, Python, Node.js, Android build tools, and the repository’s vendored CodexApp runtime.
- An OpenRouter API key supplied locally; never commit it.
- For the optional exact Dolphin X1 405B route: the paired Windows PC, private Tailscale connectivity, approximately 171 GB temporary free storage while the verified shards are merged, at least 96 GB system RAM, and a CUDA GPU. The checked-in `windows/` scripts pin shard checksums, bind only to the paired Tailscale address, and scope the firewall rule to the Tailscale CGNAT range.

Clone or place the repository at the exact runtime path:

```text
/data/data/com.termux/files/home/nemotron-unrestricted-app
```

Create the private credential file from the example and restrict it to the current Termux user:

```bash
./bootstrap-nemotron-runtime.sh
cp runtime-template/.codex/openrouter.env.example runtime/.codex/openrouter.env
chmod 600 runtime/.codex/openrouter.env
```

Set `OPENROUTER_API_KEY` in that private file. The proxy audit records model, status, timing, routing, repair, and retry metadata; it does not record prompts or responses.

## Build and install

The public tree does not contain a private signing key. Generate a local key once:

```bash
./generate-signing-key.sh
```

Keep `build/nemotron-unrestricted.keystore` and `build/signing.properties` private and backed up. Android upgrades require the same signer; losing it prevents in-place upgrades.

Build and verify:

```bash
./bootstrap-nemotron-runtime.sh
./validate-nemotron-sources.sh
./scan-nemotron-secrets.py
python -m unittest discover -s tests -v
./isolation-preflight.sh
./build-nemotron-unrestricted.sh
```

`scan-nemotron-secrets.py` without arguments also scans reachable Git history and is required before publication. The build repeats a fail-closed current-tree, staged-path, and signed-APK scan so a private in-place update does not read ignored runtime credentials or signing files. If the history scan reports a legacy finding, do not push that history; sanitize it in a separately authorized history-rewrite or clean public branch workflow first.

For an in-place release with a credential-excluding state manifest, use the release gate before the signer-pinned install step:

```bash
./release-nemotron-gate.sh \
  --manifest /path/to/before.sha256 \
  --manifest-cwd /path/used-when-the-manifest-was-captured
```

`--local-private` is only for a local installation after a full history scan has already identified legacy history that is not publishable; it never makes that history safe to push.

Capture a fresh manifest immediately before that gate when no valid external manifest remains. It hashes sessions, archived sessions, and workspace files only; `state_5.sqlite` is enumerated read-only by the verifier but excluded by default because a live runtime may legitimately update its SQLite/WAL bookkeeping without changing preserved chat records.

```bash
./capture-nemotron-preservation.py \
  --output build/release-evidence/preservation-before-install.sha256
```

Install without uninstalling or clearing data. Pin the certificate already installed for this package as well as the new APK checksum:

```bash
EXPECTED_SIGNER_SHA256="$(codex-package inspect com.michaelovsky.nemotronunrestricted.isolated | jq -r .signerSha256)"
codex-install dist/Nemotron-Unrestricted-1.9.0.apk \
  --package com.michaelovsky.nemotronunrestricted.isolated \
  --signer "$EXPECTED_SIGNER_SHA256" \
  --sha256 "edf81d2ce9a6caaf302b3872fd5f4d35d13e4fa0b4f8456eea7d64f7b8bdeb2f"
```

The maintained personal build uses its existing historical upgrade-compatible certificate. A locally generated public-source build has a different signer and cannot upgrade that personal installation without uninstalling it; uninstalling would remove Android app data and is not part of the supported upgrade workflow.

## Runtime verification

For ordinary user verification after installation, open the app with:

```bash
codex-android open com.michaelovsky.nemotronunrestricted.isolated
codex-android current
```

Automated release acceptance does not require stealing the physical foreground: package replacement runs the real WebView on a private `OWN_CONTENT_ONLY` presentation display and records `NemotronHeadlessProof`. Then read `runtime/.codex/supervisor/ports.env` and verify:

- GUI `/codex-api/rpc` returns the expected custom-provider configuration.
- Proxy `/vault-health` reports `app=nemotron-unrestricted`, provider/model/tool model, credential state, dynamic ports, and source hash.
- Supervisor `/health` reports the same app identity, source hash, completion/progress sequences, and counts; `/progress` provides bounded ordered readback.

## State, privacy, and boundaries

Sessions, memories, databases, logs, workspace state, credentials, and signing files are excluded from the public tree. The runtime uses project-local writable roots and does not trust sibling application source directories. Back up `runtime/.codex` before upgrades; never clear package data or uninstall as a repair step.

Streaming is validation-first. For ordinary streamed turns, the local proxy can emit keepalive comments while it buffers and validates the complete upstream response before releasing model bytes. Tool-bearing and tool-result requests are intentionally non-streaming upstream and are translated into synthetic response events only after the validated response is complete. The UI must not present these paths as progressive upstream tool streaming.

“Unrestricted” is an application behavior claim, not a promise of unlimited access or zero refusals. The app does not bypass logins, MFA, CAPTCHAs, payments, device locks, provider enforcement, Android permissions, target authorization, or missing kernel/hardware features. Active security diagnostics require ownership or explicit authorization.

## Licensing and third-party code

Project-authored code is MIT licensed; see `LICENSE`. Vendored packages retain their own licenses, including the MIT-licensed CodexApp package and transitive dependency notices under `vendor/`. See `THIRD_PARTY_NOTICES.md`.
