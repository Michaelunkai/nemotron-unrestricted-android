# Nemotron Unrestricted Capability Catalog

This catalog describes the broad supported command surface for the isolated Nemotron Android agent. Commands execute with project-local `HOME`, `CODEX_HOME`, sessions, workspace, skills, memories, downloads, and runtime state. The agent acts autonomously on legitimate requests, uses the least restrictive safe route available, and states exact external authorization or Android consent boundaries instead of inventing capabilities.

## Identity and runtime

- Project: `/data/data/com.termux/files/home/nemotron-unrestricted-app`
- Android package/activity: `com.michaelovsky.nemotronunrestricted.isolated/.MainActivity`
- Isolated state: `runtime/home`, `runtime/.codex`, and `workspace`
- Default dynamic ports: GUI `5903`, proxy `18774`, supervisor `18775`; the selected distinct loopback ports are persisted in `runtime/.codex/supervisor/ports.env`.
- PATH order: project `bin`, Termux `/data/data/com.termux/files/usr/bin`, then the global capability broker. Project `rg` and `ripgrep` exec the working Termux binary by absolute path.

## Planning, coding, terminal, and Git

- Use the agent plan/checklist for multi-step work and keep one active step.
- Shell, Python, Node.js, Java/JDK, Git, curl, jq, OpenSSL, Android build tools, apktool, aapt, apksigner, zipalign, d8, Nmap, YARA, Radare2, GDB, and strace are available when `command -v` confirms them.
- Work only inside the requested repository or explicit target. Preserve dirty user changes and verify edits with syntax checks, tests, `git diff --check`, and focused readback.
- Use `rg` or `ripgrep` for project search. The local shim intentionally bypasses an incompatible vendored ELF binary.
- Use ordinary local `git` for this Android repository. Use `codex-github` only for paired-PC Git/GitHub work.

## Web research, fetch, browser, and APIs

- `codex-search '<query>'`: headless web discovery.
- `codex-source`, `codex-fetch <url>`, curl, and Python HTTP clients: source and API retrieval.
- `codex-browser` and browser automation: interactive sites, visible flows, screenshots, and DOM-backed verification when headless retrieval is insufficient.
- `codex-open-url <url>`: verified Android VIEW intent when visible browser/app routing is part of the task.
- Prefer official documentation and primary sources. Record final URLs, timestamps, checksums, and observed limitations rather than inferring access.

## Downloads and artifacts

- `codex-download <url> [output] [--output path] [--sha256 digest] [--retries N]`: confined, retrying acquisition.
- Outputs are restricted to isolated runtime downloads, the project workspace, or Android Download. Existing targets, symlinks, protected sibling paths, and ambiguous dual output syntax are refused.
- The wrapper delegates with isolated `HOME`, `CODEX_HOME`, and provenance state, then independently verifies the exact output path, byte count, content validation, and SHA-256.
- `codex-artifact inspect <path>` and `codex-artifact sign-check <apk>`: artifact metadata and APK signature inspection.
- Never treat an HTML error page, redirect receipt, downloader exit code, or installer launch as artifact/install proof.

## Android packages and verified APK installation

- Begin visible Android work with `codex-android capabilities`, resolve the package, then inspect the fresh foreground state.
- `codex-android packages [fragment]`: exact `pm list packages --user 0` inventory through isolated Shizuku/rish.
- `codex-package inspect|verify <package>`: stable package paths, base APK SHA-256, signer certificate SHA-256, signature status, version, permissions, and system/protected classification.
- `codex-pm <arguments>`: guarded package-manager route. Direct install/uninstall actions are redirected to the verified wrappers.
- `codex-install <apk-or-url> --package <id> --signer <certificate-sha256> [--sha256 digest]`: inspect, pin, stream with exact size, and independently read back installed path/hash/signer/version. URL installs always require package and signer pins.
- `codex-uninstall <package>`: uninstall any non-protected package. Protected: this app, Termux, Shizuku, and Android system apps.

## Android UI and Shizuku

- `codex-android open <package-or-fragment>` resolves a launchable activity, starts it, and verifies the fresh resumed package.
- `codex-android current`, `dump`, `screenshot`, `tap`, `longtap`, `swipe`, `text`, `key`, and `keyevent` provide UI state and actions.
- Prefer semantic UI selectors through the Android automation surface; coordinates require fresh bounds and a postcondition.
- `codex-shizuku status|stage|test` verifies shell UID, SELinux state, explicit remote status, and the isolated rish bridge.
- `bin/rish` validates its isolated runtime assets against pinned provenance before use.

## Device APIs, files, media, and documents

- Termux:API commands include camera photo, clipboard get/set, location, notifications, battery, vibration, torch, volume, Wi-Fi connection data, TTS, toast, and sharing.
- `codex-gallery recent|search` inventories MediaStore images/videos with exact IDs, names, relative paths, timestamps, MIME types, and sizes; `inspect` and `open` operate on one verified ID.
- `codex-gallery delete` requires exact ID-bound confirmation and moves the item to Android MediaStore trash; `restore` untrashes that exact ID. Both actions are audited and independently verified.
- `codex-gallery faces` performs local-only Android face-presence counting. `codex-gallery semantic` uses the current verified zero-price vision route for visible object/scene/text matching. Neither route claims identity or sensitive-attribute inference.
- Image attachments are routed only to a live-catalog model whose input modalities include images, whose output includes text, and whose current prompt/completion price is zero. Text-only requests remain on the selected text model. The bundled conversation UI renders local attachments and completed image output items in the same session.
- Use installed media/document tools for metadata, OCR, conversion, archives, PDFs, images, audio, and video after checking their exact command/version.
- Keep generated artifacts under the workspace or an explicitly requested safe output path. Do not overwrite unrelated work; use checksums and reopen/parse generated documents before claiming success.
- For Android screenshots, capture to one exact shared path, copy/read it safely, and verify the PNG signature.

## Networking and security testing

- `codex-wifi-scan`: serialized Wi-Fi connection and scan-result reading with bounded cache fallback. Never call the device-crashing `cmd wifi start-scan` route.
- `codex-lan-discover --neighbors` or `--scope <CIDR>`: passive neighbor inventory or an explicitly authorized scope.
- `codex-pentest`, Nmap TCP-connect scans, DNS/dig/WHOIS, TLS/OpenSSL, netcat/socat, YARA, Radare2, GDB, strace, apktool, and static APK analysis support authorized diagnostics.
- Require an explicit target before active probing. Use bounded retries, rate limits, exact targets, and postconditions. After three identical failures, change strategy.

## Paired Windows, PowerShell, Git, and GitHub

- `codex-win '{"action":"status"}'` [--timeout N]: paired gateway health.
- `powershell|pwsh -Command|-c|-lc '<command>'`: compatibility route. Dynamic invocation, encoded, file/stdin, and ambiguous commands are blocked locally before the gateway.
- `powershell|pwsh --cleanup '<structured-json>'`: the Windows deletion route with classified targets through inventory, classification, protected-path exclusion, manifest, execution, verification, and per-target receipts.
- `codex-github status`: one redacted JSON status record.
- `codex-github run '<direct git-or-gh command>'`: dedicated direct command route. Credentials remain in the paired PC credential manager.

## Persistent jobs, recovery, goals, and learning

- `codex-job`, `codex-goal`, scheduling, audit, undo/restore, health, verify, and recover commands provide durable work coordination.
- `codex-learn` and `codex-lessons` record exact failure/root-cause/corrected-rule lessons under isolated memory.
- Long work must expose real progress from actual plan/tool/runtime events, preserve state across reconnect/restart, detect inactivity, inspect current state, and change strategy.
- Active turns are persisted by the supervisor and polled independently of the WebView. The foreground service remains sticky and boot-restored; successful authoritative completion events produce one three-second notification-stream tone at relative volume 50 while respecting Android mute/DND behavior.

## Universal completion rule

For every capability, completion means: the action was authorized, the command route was validated, the requested effect was independently observed, and the final report distinguishes verified results from unavailable external gates.
