# Nemotron Unrestricted Capability Catalog

This catalog describes the broad supported command surface for the isolated Nemotron Android agent. Commands execute with project-local `HOME`, `CODEX_HOME`, sessions, workspace, skills, memories, downloads, and runtime state. The agent acts autonomously on legitimate requests, uses the least restrictive safe route available, and states exact external authorization or Android consent boundaries instead of inventing capabilities.

The catalog is model-independent. Every selectable model receives the same developer instructions and synchronized agent contract; if a selected model cannot call tools, the proxy routes only the tool-bearing turn to a currently verified tool-capable model while preserving the transcript, instructions, attachments, approvals, plan, and real-time English progress contract.

## Identity and runtime

- Project: `/data/data/com.termux/files/home/nemotron-unrestricted-app`
- Android package/activity: `com.michaelovsky.nemotronunrestricted.isolated/.MainActivity`
- Isolated state: `runtime/home`, `runtime/.codex`, and `workspace`
- Default dynamic ports: GUI `5903`, proxy `18774`, supervisor `18775`; the selected distinct loopback ports are persisted in `runtime/.codex/supervisor/ports.env`.
- PATH order: project `bin`, Termux `/data/data/com.termux/files/usr/bin`, then the global capability broker. Project `rg` and `ripgrep` exec the working Termux binary by absolute path.
- `codex-doctor all|environment|toolchain|freshness|android|performance [--versions] [--json]` performs a read-only readiness inspection. It reports exact paths, optional gaps, locally indexed upgrades, runtime versions, project-tool hashes, storage mappings, Shizuku/package/battery-optimization readback, memory, storage, zram, and thermal data without refreshing registries, installing packages, changing Android settings, opening an app, or treating an installed command as permission proof.
- `codex-maintain check` remains read-only. `codex-maintain plan --output <isolated-path>` creates a fresh hashable plan; `apply --plan <path> --confirm-sha256 <hash> --yes` serializes execution, backs up package-manager state, refreshes the index, refuses any simulated removal, applies only a no-removal upgrade, and requires post-upgrade doctor verification. A backup is diagnostic and rollback-aware, not a false guarantee that every upstream version remains downloadable.
- `codex-automation health|cache|circuit|increment|gauge|log` provides migrated SQLite TTL state, atomic cache updates, expiry pruning/vacuum, closed/open/half-open circuit state, correlated and recursively redacted JSONL events with bounded rotation, and prompt-free Prometheus counter/gauge metrics for outcomes, queue depth, latency, retries, and verification. Shared retry helpers require an explicit retry-safe declaration and use bounded exponential backoff with jitter.
- `codex-boot status|generate|enable|disable` manages one exact optional Termux:Boot script. Generation is inert; enable/disable requires the generated SHA-256, never overwrites unrelated startup content, and starts only the selected SSH-agent or bounded PC-monitor profile. It never creates a permanent wake lock.
- `codex-storage status|enable|disable` manages exact reversible links for shared storage, Downloads, Pictures, DCIM, Movies, and Music in both Termux and the isolated runtime. It refuses existing files/directories or unexpected symlinks; disable unlinks only exact managed links and never deletes shared content.
- `codex-battery status|enable|disable` reads and reversibly manages battery-optimization exemptions only for Termux and Nemotron. Enable records the prior state; disable removes only exemptions that this command added.
- `codex-task validate|dry-run|run|resume|status|cancel` executes schema-validated JSON/YAML task definitions through `codex-exec`. Every step has an English purpose and mandatory independent postcondition; retries require a safe declaration; mutation/consent/rollback metadata is visible; checkpoints are atomic and cancellation terminates the active process group.
- `codex-schedule create|list|status|pause|resume|cancel|run-now` binds verified task files to Android JobScheduler using exact job IDs, ≥15-minute periods, network/charging/battery/storage/persistence constraints, missed-run catch-up or skip policy, durable receipts, and exact cancellation. Future one-shot jobs self-check their due time and cancel themselves after one verified run.
- `codex-pc status|diagnostics|query --command <PowerShell>` constructs gateway JSON as one direct argument, never through shell interpolation. It classifies policy, transport, process, identity, and postcondition failures and supports required output or exact JSON-field postconditions.
- `codex-pc-monitor run-once|start|status|stop` serializes fresh diagnostics, records latency and consecutive failures, resets only after a verified receipt, and optionally emits one high-priority Android notification after three failures with a 15-minute alert cooldown.
- `codex-pc-route status|select` compares only authenticated identity-verified routes: the signed gateway, strict-known-host batch SSH/SFTP, HTTPS with a pinned public key, or authenticated SMB with signing. It measures latency and retains a healthy prior route within 20% of the fastest for five minutes to prevent flapping.
- `codex-inventory refresh|status` stores only safe gateway identity/version markers, capability IDs/statuses/commands, environment readiness, and package names/versions. TTLs are five minutes for gateway identity, one hour for capabilities/environment, and twelve hours for packages; identity changes invalidate gateway and route caches.
- `codex-dashboard start|status|stop` optionally serves only `127.0.0.1`. It exposes health, prompt-free metrics, a strict projection of recent redacted events, and inventory counts/freshness—never raw inventory values, prompts, command/model output, credentials, or directory contents.
- `codex-registry refresh|status|search` validates skill front matter, plugin identity/version and contained skill paths, capability command availability, hashes, limits, and duplicates using manifests/documentation only. Discovery never imports or executes startup hooks, scripts, plugin code, or binaries.
- `codex-research search|fetch` adds validated domain/keyword filters, bounded paging over the provider result window, per-domain throttling, retries, `Retry-After` evidence, and URL/title/rank/provider/status/time provenance to the installed provider-fallback search/fetch routes.
- `codex-browser-safe` performs deterministic headless static-HTML navigation, scoped selector waits, form filling/submission, link following, downloads, allowlisted text/title/location evaluation, and PNG/PDF evidence. It keeps cookies within one run, verifies every response and artifact hash, and fails explicitly instead of pretending that JavaScript-only interactions completed.
- `codex-artifacts add|inspect|quarantine|restore|promote|rollback|prune` manages immutable hashed copies with source provenance. Promotion atomically backs up and verifies an exact target; rollback refuses a target changed since promotion; retention is inactive-only and requires the exact current plan hash.
- `codex-download` confines destinations, refuses credentialed URLs/symlink escapes/existing outputs, bounds retries/time/bytes, verifies redirects, hashes local readback, and cleans partial failures. `codex-install` verifies APK identity/signature/hash, requires package and signer pins for URLs and self-updates, blocks downgrades before mutation, silently replaces in place, and independently reads back installed version, bytes, hash, signer, and permissions.
- `codex-scaffold list|create|verify|rollback` provides reviewed Python, Node, dependency-free Node full-stack, installable PWA, shell, C17, C++17, static web, Go, Rust, Java, and PowerShell templates. Creation validates a workspace-confined new target, tests in staging, initializes Git, hashes the generated tree, and records rollback metadata; rollback refuses any project changed after creation.
- `codex-toolchain inspect|verify` detects and verifies Python, Node.js, shell, C, C++, Java, Kotlin, Android, PowerShell, and static-web projects. Adapters use fixed argv or bounded parsers, avoid dependency installation and build-tree mutation, hash verified inputs, expose native-runtime readiness separately, and fail explicitly when an optional compiler is absent.
- `codex-pipeline plan|run|rollback` accepts a strict check/deploy manifest, produces a dry-run plan hash, executes only fixed language adapters, logs English gate results, atomically copies static output, verifies the full target tree, preserves the prior target, and refuses rollback after any unrecorded target change.
- `codex-release plan|prepare|asset|rollback` enforces increasing semantic/version codes, exact plan hashes, synchronized manifest/build/gate versions, changelog and release notes, unchanged-file rollback, and APK package/version/signature/signer/size/SHA-256 metadata before publication.
- `codex-deploy status|plan|run` discovers already authenticated Vercel, Cloudflare Pages, and Netlify CLIs, hashes the exact workspace-confined source tree, requires the exact plan hash, deploys non-interactively only through a ready account, verifies the resulting public HTTPS body, and records a receipt. Missing CLI/account authorization is reported as the real external gate; it never fabricates a deployment or silently creates credentials.
- `codex-trip create|verify` produces a resumable, hash-verified travel pack with machine-readable inputs, an itinerary, calendar file, encoded Maps handoff, model action commands, and current research queries. Optional `--research` executes bounded headless searches with factual per-query English progress and stores timestamped source evidence without claiming availability, prices, or bookings that were not verified.
- `codex-intent open-url|open-app|settings|share-text|view|map-search|directions|calendar-event|capture-image` builds typed Android activity specs for common workflows. Travel actions use encoded, API-key-free Google Maps URLs and typed calendar insertion; default mode resolves without opening UI and execution is explicit. It forbids file/credentialed URIs, supports typed content-URI output, redacts payload values from receipts, and delegates to `codex-android` postcondition verification.
- `codex-ui-safe snapshot|suggest|explore|run` provides the Shizuku/uiautomator fallback when the richer accessibility broker is absent. `suggest` ranks fresh non-password targets using normalized visible labels, descriptions, resource IDs, classes, and conservative common-action equivalents. `explore` performs bounded package-scoped scrolling and stops on repeated hierarchy hashes, close ties, package drift, or its declared limit. Workflows support click, long-click, text, swipe, back, and wait; they remain retry bounded, postcondition mandatory, and allow coordinates only as an explicit fallback. PNG/XML evidence is decoded/parsed and hashed rather than inferred from command status.
- `codex-device refresh|status|search|permissions` stores TTL-bound Android identity, user-0 packages, hardware/software features, Termux API commands, and readiness. `permissions` uses a guarded, remotely and locally SHA-256-verified staged package dump; it distinguishes install grants from user-0 runtime grants, ignores other-user overrides, retains custom permissions, and maps grants to truthful device-action readiness without prompting or changing settings. The raw build fingerprint is hashed; identity changes invalidate dependent records; Shizuku, storage, battery, and package readiness come from verified read-only receipts.
- `codex-netdiag dns|tcp|https|route|wifi|pc|all` performs bounded read-only diagnostics with latency and actionable DNS/refused/timeout/route/TLS/HTTP/transport categories. Wi-Fi identifiers are hashed only when Android exposes real values, route visibility limitations are explicit, and paired-PC identity is read from a verified fresh diagnostics receipt.
- `codex-secrets set|rotate|list|status|run|delete|restore` derives an AES-256-GCM envelope key from a non-exportable Android Keystore RSA signature. Values enter through stdin only; metadata enforces scopes and executable names; process injection redacts exact values from output; rotation archives only ciphertext; deletion is recoverable.
- `codex-security audit|artifact` combines runtime/package readiness, manifest-only registry state, read-only routes, current secret scan, destructive-command denial probes, private file modes, and managed-artifact integrity. Artifact inspection hashes and bounds archives without extraction, refusing traversal, absolute paths, archive links, expansion bombs, and symlink inputs.
- `codex-command register|list|plan|run|status|cancel|rollback` turns validated task definitions into reusable personal commands. It enforces read/mutation/external consent classes, mandatory rollback coverage for mutation, idempotency keys, task-process cancellation, verified postconditions, reverse-order rollback, metadata-only listing, and fail-closed receipts.
- `codex-files inspect|checksum|copy|archive-list|archive-create|archive-extract` confines operations to managed project/runtime roots, refuses protected private paths, symlinks, traversal, archive links, expansion excess, existing destinations, and unverified copies. ZIP creation is reopened and extraction is staged, atomically promoted to a new directory, and checked file by file.
- `codex-device-io status|clipboard-get|clipboard-set|notify|toast|tts|media|volume` provides typed Termux API routes. Text-bearing mutations accept content through stdin and redact it from receipts; clipboard and volume mutations require exact readback; playback files are verified regular paths; status is read-only and never opens the app.
- `codex-care status|backup|verify|restore|recovery-drill|retention-plan|retention-apply|upkeep-plan|upkeep-apply|database-check` creates authenticated AES-256-GCM backups using stdin-only passphrases and scrypt, verifies each archived file, restores only into a new isolated destination, and drills recovery without touching live state. Retention moves unchanged hash-planned backups to recoverable retired storage; upkeep backs up SQLite before exact cache pruning/vacuum, checks integrity, and retires only unchanged old logs.
- `codex-resilience safe-mode|sync-plan|sync-apply|review|health|recover-local-state` provides an exact hash-reversible local-only mode, non-destructive checksum sync with explicit conflict copies, bounded redacted event self-review, combined read-only health, and cache-database corruption quarantine/rebuild. Local-only mode is enforced by research, remote browser, download, URL install, paired-PC, and Windows wrappers; loopback browser checks and local APK inspection remain available.

## Planning, coding, terminal, and Git

- Use the agent plan/checklist for multi-step work and keep one active step.
- `codex-exec -- <program> <arg>...` runs an explicit argv without an implicit shell. Complex commands use a prepared `codex-exec --script <path>` script and mandatory Bash syntax preflight; JSON request files add an English purpose, bounded timeout, retry-safety declaration, optional `wakeLock:true` with guaranteed release, and independent output/file postconditions.
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
- `codex-android resolve-intent '<json>'` and `intent '<json>'` provide schema-validated activity, broadcast, and foreground-service intents with explicit action/data/type/categories/package/component/flags and typed extras. File URIs, control characters, unknown fields, and shell composition are rejected.
- Prefer semantic UI selectors through the Android automation surface; coordinates require fresh bounds and a postcondition.
- Default routing is typed intent or deep link → package open → fresh UI dump and semantic action → guarded Shizuku shell → visible browser fallback. Authentication, device-lock, payment, consent, and Android secure surfaces remain explicit platform gates and are never bypassed.
- `codex-shizuku status|stage|test` verifies shell UID, SELinux state, explicit remote status, and the isolated rish bridge.
- `bin/rish` validates its isolated runtime assets against pinned provenance before use.

## Device APIs, files, media, and documents

- Installed Termux:API discovery covers audio/battery/brightness, camera, clipboard, contacts/call log, dialogs, biometrics, infrared, jobs, keystore, location, media, microphone, NFC, notifications, SAF documents, sensors, sharing, SMS, speech/TTS, storage, telephony, toast, torch, USB, vibration, volume, wake lock, wallpaper, and Wi-Fi data. Hardware, Android permission, foreground, and user-consent requirements are checked at execution time; an installed command is never presented as proof that a device feature is available.
- `codex-gallery recent|search` inventories MediaStore images/videos with exact IDs, provider paths, relative paths, timestamps, generations, MIME types, and sizes through hash-verified staged readback. Query fields adapt across Android API 23–36+, and root-storage media is preserved without weakening traversal checks; `inspect` and `open` operate on one verified ID.
- `codex-gallery metadata|ocr|ocr-search|export|share` reads exact EXIF/container metadata; transcribes visible text locally with Tesseract word confidence/bounds and a generation-keyed SQLite WAL cache; searches OCR text in resumable inline-rendered pages without uploading images; creates checksum-verified non-destructive originals or JPEG/PNG/WebP copies; and dispatches Android shares while reporting any remaining user target-selection gate. Exact OCR uses the verified vision route only when the local engine is unavailable or fails.
- `codex-gallery delete` requires exact ID-bound confirmation and moves the item to Android MediaStore trash; `restore` untrashes that exact ID. Both actions are audited and independently verified.
- `codex-gallery faces` performs local-only Android face-presence counting in eight-image batches, retries omitted detector receipts individually, paginates with exact offsets, and returns a versioned MediaStore-bound receipt that the conversation automatically renders as lazy visible images with full-size viewing. `codex-gallery semantic` provides the same pagination/rendering contract through the current verified zero-price vision route for visible object/scene/text matching. “All/every” requests continue identical pages until `hasMore:false`. Neither route claims identity or sensitive-attribute inference.
- Image attachments are routed only to a live-catalog model whose input modalities include images, whose output includes text, and whose current prompt/completion price is zero. Text-only requests remain on the selected text model. The bundled conversation UI renders local attachments and completed image output items in the same session.
- Use installed media/document tools for metadata, OCR, conversion, archives, PDFs, images, audio, and video after checking their exact command/version.
- Keep generated artifacts under the workspace or an explicitly requested safe output path. Do not overwrite unrelated work; use checksums and reopen/parse generated documents before claiming success.
- For Android screenshots, capture to one exact shared path, copy/read it safely, and verify the PNG signature.

## Networking and security testing

- `codex-wifi-scan`: serialized Wi-Fi connection and scan-result reading with bounded cache fallback. Never call the device-crashing `cmd wifi start-scan` route.
- `codex-lan-discover --capabilities|--self|--neighbors|--scope <CIDR>|--tcp <host> <ports>|--pc`: installed route discovery, Android address/route state, passive neighbors, bounded local-scope discovery, explicit TCP checks, and exact paired-PC diagnostics with English receipts.
- SSH/SCP/SFTP support authenticated file transfer when an explicit endpoint and host identity are available; destination checksum/readback is required. Git worktrees plus `codex-exec` support project creation/build/test workflows; `codex-browser` supports DOM-backed browser workflows.
- `codex-pentest`, Nmap TCP-connect scans, DNS/dig/WHOIS, TLS/OpenSSL, netcat/socat, YARA, Radare2, GDB, strace, apktool, and static APK analysis support authorized diagnostics.
- Require an explicit target before active probing. Use bounded retries, rate limits, exact targets, and postconditions. After three identical failures, change strategy.

## Paired Windows, PowerShell, Git, and GitHub

- `codex-win '{"action":"status"}'` [--timeout N]: paired gateway health.
- `codex-win '{"action":"diagnostics"}'` [--timeout N]: exact verified listener, dynamic Tailscale address, process identity, elevation, and start-time receipt.
- `powershell|pwsh -Command|-c|-lc '<command>'`: compatibility route. Dynamic invocation, encoded, file/stdin, and ambiguous commands are blocked locally before the gateway.
- `powershell|pwsh --cleanup '<structured-json>'`: the Windows deletion route with classified targets through inventory, classification, protected-path exclusion, manifest, execution, verification, and per-target receipts.
- `codex-github status`: one redacted JSON status record.
- `codex-github run '<direct git-or-gh command>'`: dedicated direct command route. Credentials remain in the paired PC credential manager.

## Live provider, model, and effort identity

- `codex-runtime-status`: authoritative selection state plus requested gateway/model/effort/budget and separately provider-confirmed gateway/provider/model/effort/usage, request/response IDs, active-turn count, and no-substitution readback from the local proxy. Unknown effective values remain null.
- `Max` is represented at the OpenRouter wire boundary as the documented 128,000-token reasoning budget; the status receipt reports both `effort=max` and `reasoningBudget=128000`.
- Mid-turn changes are scoped to one registered active thread/turn, persist the exact new selection, and stop the current provider call exactly once. The next explicit continuation uses the new runtime without approval resolution, tool execution, mutation replay, or replacement-turn creation.

## Persistent jobs, recovery, goals, and learning

- `codex-job`, `codex-goal`, scheduling, audit, undo/restore, health, verify, and recover commands provide durable work coordination.
- `codex-learn` and `codex-lessons` record exact failure/root-cause/corrected-rule lessons under isolated memory.
- Long work must expose real progress from actual plan/tool/runtime events, preserve state across reconnect/restart, detect inactivity, inspect current state, and change strategy.
- Active turns are persisted by the supervisor and polled independently of the WebView. The foreground service remains sticky and boot-restored; completed, failed, and manually stopped outcomes each produce one app-specific six-note PCM notification ringtone with exactly 144,000 samples at 48 kHz and per-track gain 0.5, while respecting Android mute/DND behavior.

## Universal completion rule

For every capability, completion means: the action was authorized, the command route was validated, the requested effect was independently observed, and the final report distinguishes verified results from unavailable external gates.
