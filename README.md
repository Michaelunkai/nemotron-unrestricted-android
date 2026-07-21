# Nemotron Unrestricted for Android

Nemotron Unrestricted is an independent Android launcher and Termux-hosted agent workspace for OpenRouter models. The local proxy adds no prompt/response content classifier; it provides OpenAI-compatible routing, bounded retries, tool-schema repair, and metadata-only auditing. Provider behavior, account access, Android permissions, target authorization, and hardware limits still apply.

## Download the Android APK

The public source repository is [Michaelunkai/nemotron-unrestricted-android](https://github.com/Michaelunkai/nemotron-unrestricted-android). The universal Android 1.0.0 APK is available from the [v1.0.0 release](https://github.com/Michaelunkai/nemotron-unrestricted-android/releases/tag/v1.0.0):

- [Download Nemotron-Unrestricted-1.0.0.apk](https://github.com/Michaelunkai/nemotron-unrestricted-android/releases/download/v1.0.0/Nemotron-Unrestricted-1.0.0.apk)
- SHA-256: `c604f0b456428b9fdf3bb62917789b07d5f3e44e9f5c6772581d20b96cdf0385`
- Signing certificate SHA-256: `f9eddd82a7fe4e0ce902f956e35f29dbaea2b7cd97f33f29fa323945a7df528f`

Android users can download and install the APK on compatible devices after allowing installation from their chosen browser/file manager. The APK is the launcher and lifecycle manager; full agent operation also requires the Termux-hosted repository/runtime, local credentials, permissions, and—only for exact Dolphin X1—the paired-PC setup described below. Installing the APK alone does not bundle an 85 GB model or bypass Android/provider requirements.

## Identity and architecture

- Android package: `com.michaelovsky.nemotronunrestricted.isolated`
- Activity: `.MainActivity`
- Version: 1.0.0 (`versionCode 1`)
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
- Live progress overlay with visible-thread scoping, one-second elapsed time, three-second reconciliation, exact-turn filtering, plan/action/failure counts, latest verified result, next action, and expandable technical details.
- Durable metadata-only completion ledger with deduplication and restart-safe sequencing.
- Guarded Android package controls that refuse destructive actions against the original Codex app, Codex Frontier, the NVIDIA app, Termux, Shizuku, and Android system packages.
- Project-local Android, web, confined download, signer-pinned APK, Wi-Fi, LAN, and authorized diagnostic workflows. See `capabilities/CAPABILITY_CATALOG.md` for the exact command surface.
- Fail-closed read-only Windows PowerShell routing, a separate direct Git/GitHub route, and a structured receipt-backed cleanup workflow; caller-authored deletion and encoded/dynamic/nested shell invocation are rejected before the paired gateway.

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
codex-install dist/Nemotron-Unrestricted-1.0.0.apk \
  --package com.michaelovsky.nemotronunrestricted.isolated \
  --signer "$EXPECTED_SIGNER_SHA256" \
  --sha256 "$(awk '{print $1}' dist/Nemotron-Unrestricted-1.0.0.apk.sha256)"
```

The maintained personal build uses its existing historical upgrade-compatible certificate. A locally generated public-source build has a different signer and cannot upgrade that personal installation without uninstalling it; uninstalling would remove Android app data and is not part of the supported upgrade workflow.

## Runtime verification

After the offline build and preservation checks pass, open the app with:

```bash
codex-android open com.michaelovsky.nemotronunrestricted.isolated
codex-android current
```

Then read `runtime/.codex/supervisor/ports.env` and verify:

- GUI `/codex-api/rpc` returns the expected custom-provider configuration.
- Proxy `/vault-health` reports `app=nemotron-unrestricted`, provider/model/tool model, credential state, dynamic ports, and source hash.
- Supervisor `/health` reports the same app identity, source hash, sequence, and completion count.

## State, privacy, and boundaries

Sessions, memories, databases, logs, workspace state, credentials, and signing files are excluded from the public tree. The runtime uses project-local writable roots and does not trust sibling application source directories. Back up `runtime/.codex` before upgrades; never clear package data or uninstall as a repair step.

“Unrestricted” is an application behavior claim, not a promise of unlimited access or zero refusals. The app does not bypass logins, MFA, CAPTCHAs, payments, device locks, provider enforcement, Android permissions, target authorization, or missing kernel/hardware features. Active security diagnostics require ownership or explicit authorization.

## Licensing and third-party code

Project-authored code is MIT licensed; see `LICENSE`. Vendored packages retain their own licenses, including the MIT-licensed CodexApp package and transitive dependency notices under `vendor/`. See `THIRD_PARTY_NOTICES.md`.
