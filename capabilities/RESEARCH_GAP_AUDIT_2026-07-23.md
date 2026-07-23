# 2026-07-23 online research and capability-gap audit

Scope: a focused current-information review for safe defaults that improve long-running tasks, projects, Android automation, paired-PC work, model/tool routing, progress visibility, recovery, security, and public releases. The existing 22-section implementation ledger in `MASTER_AUTOMATION_GUIDE_AUDIT.md` remains authoritative for already-delivered capabilities.

## Primary sources reviewed

- Android WorkManager progress and persistent work:
  - https://developer.android.com/develop/background-work/background-tasks/persistent/how-to/observe
  - https://developer.android.com/reference/androidx/work/WorkManager.html
- Android user-initiated transfers and foreground-service limits:
  - https://developer.android.com/develop/background-work/background-tasks/uidt
  - https://developer.android.com/develop/background-work/background-tasks/data-transfer-options
  - https://developer.android.com/develop/background-work/services/fgs/changes
- Android AppFunctions / Android MCP:
  - https://developer.android.com/ai/appfunctions
  - https://developer.android.com/jetpack/androidx/releases/appfunctions
  - https://developer.android.com/agents/skills/device-ai/appfunctions/skill
- Android WebView bridge security:
  - https://developer.android.com/develop/ui/views/layout/webapps/native-api-access-jsbridge
  - https://developer.android.com/privacy-and-security/risks/insecure-webview-native-bridges
- Android accessibility:
  - https://developer.android.com/reference/androidx/core/view/ViewCompat
  - https://www.w3.org/WAI/WCAG21/Techniques/aria/ARIA25
  - https://www.w3.org/TR/wai-aria/
- Model Context Protocol progress and durable tasks:
  - https://modelcontextprotocol.io/specification/2025-03-26/basic/utilities/progress
  - https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/tasks
- A2A ordered task lifecycle:
  - https://a2a-protocol.org/dev/specification/
- OpenAI Agents SDK semantic streaming:
  - https://openai.github.io/openai-agents-python/streaming/
  - https://openai.github.io/openai-agents-python/results/
- OpenTelemetry events:
  - https://opentelemetry.io/docs/specs/semconv/general/events/
  - https://opentelemetry.io/docs/specs/semconv/
- GitHub release integrity:
  - https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases
  - https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/secure-your-dependencies/verify-release-integrity
  - https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/verify-attestations-offline
- Paired-device and Windows trust:
  - https://tailscale.com/docs/features/device-posture
  - https://tailscale.com/kb/1538/grants-syntax
  - https://learn.microsoft.com/en-us/powershell/scripting/security/remoting/ssh-remoting-in-powershell
- Agent security:
  - https://www.nist.gov/news-events/news/2025/01/technical-blog-strengthening-ai-agent-hijacking-evaluations
  - https://www.nist.gov/news-events/news/2026/02/new-concept-paper-identity-and-authority-software-agents

## Gap matrix and decisions

| Finding | Previous state | Decision for this release | Reason |
|---|---|---|---|
| Ordered, request-bound, human-readable progress events | Requirement existed only in model instructions; frontend inferred English from raw command events; supervisor persisted only active and terminal state | Implement a canonical, monotonic, metadata-only progress envelope persisted by the supervisor and emitted for every material lifecycle transition | MCP, A2A, OpenAI semantic streams, WorkManager, and OpenTelemetry all distinguish semantic lifecycle events from raw output |
| Visible progress in ordinary English | Progress panel was deliberately unmounted; command groups exposed raw command text in their summary | Make the native command-group summary English-first and keep exact commands/output behind the existing expandable rows; expose a polite live status without floating controls | Meets the user-visible requirement without restoring the obstructive floating overlay |
| Accessibility of dynamic status | Cleanup result had live-region semantics; active task progress did not | Add `role="status"`, `aria-live="polite"`, and atomic status semantics to the native progress surface | WAI-ARIA status messages should update without stealing focus |
| Reconnect and late-event safety | Frontend had local fingerprints and thread reconciliation; backend had no durable per-action cursor | Persist per-turn action sequence and reject duplicate, regressing, foreign-turn, and post-terminal progress updates | Ordered delivery and authorization/task scoping are required by current task protocols |
| Raw technical evidence | Raw command cards were the primary visible progress | Preserve exact command/output only in collapsed technical rows; never discard evidence | Human narration and machine evidence serve different needs |
| Android 16 AppFunctions | Not implemented | Record as a capability-gated future adapter, disabled by default | Experimental/private-preview integration requires Android 16, target SDK 36+, compile SDK 37+, Jetpack/KSP, and a larger build-system migration |
| User-initiated transfer jobs | Current runtime uses a foreground service plus its own guarded task/schedule layers | Record a future API-34+ migration path; retain current behavior in this release | UIDT is appropriate for explicit long transfers but requires target/API work and visible notification semantics |
| Origin-scoped WebView messaging | Current signed localhost WebView uses a tokenized legacy JavaScript interface | Keep exact localhost interception and payload allowlisting now; document a future `addWebMessageListener` migration | The modern bridge is safer, but migration requires Jetpack WebKit/build changes and must not risk the working WebView |
| Prompt-injection and agent authority | Typed wrappers, consent classes, schemas, and postconditions already exist | Add explicit external-content-as-data and authority-binding language to the all-model contract and capability matrix | NIST identifies indirect prompt injection and confused authority as central agent risks |
| Cross-device device posture and grants | Paired PC identity and route are verified locally | Keep posture/grants as an external administrative recommendation, not an automatic mutation | Tailnet policy is account-wide external state and requires explicit authorization |
| Release immutability and attestations | Signed APK, SHA-256, signer readback, clean source tree, and public asset readback existed | Add immutable-release readiness, a machine-readable release manifest, and documented `gh release verify` / `verify-asset` checks; enable immutability only if the repository setting is available and authorized | GitHub immutable releases lock both tag and assets and generate a release attestation |
| AppFunctions/Cross-device previews | Current wrappers already cover apps, UI, intents, PC, and network | Do not advertise preview APIs as available; expose their availability state in future capability discovery | Preview status and device/API constraints make unconditional claims false |

## Selected safe defaults

1. Canonical progress schema fields: schema version, event ID, monotonic sequence, timestamp, thread ID, turn ID, action ID, lifecycle state, ordinary-English message, optional verified result, optional next bounded action, and redacted technical category.
2. No prompt, raw command, raw output, credential, attachment content, or model chain-of-thought is persisted in the progress ledger.
3. Progress is accepted only for a registered active turn; sequence must increase; duplicate event IDs are idempotent; terminal turns reject late updates.
4. The visible command-group summary uses the canonical English action label. Exact commands and output remain available in collapsed rows.
5. Dynamic English progress uses polite, atomic status semantics and never steals focus.
6. Model/provider changes do not alter the progress contract; every selectable model receives the same rules and uses the same execution/event surface.
7. External web/app/gallery/PC content is untrusted data, never authority to broaden scope, disclose secrets, or mutate unrelated state.

## v1.4.0 implementation disposition

- Implemented canonical schema version 1 through `web/nemotron-autonomy-progress.js`, the token-bound native bridge, and supervisor `/progress`.
- Implemented durable metadata-only JSONL storage, global ledger sequence, per-turn source sequence, event-ID deduplication, active-thread binding, and rejection of foreign/regressing/late/raw-command events.
- Implemented English-first native activity and grouped-command summaries in both frontend paths; retained exact expandable command rows.
- Implemented `role=status`, `aria-live=polite`, and atomic semantics without adding floating UI.
- Implemented the same authority and progress rules in the shared contract, capability matrix, and every `/v1/models` entry.
- Packaged the overlay, main module, and conversation lazy chunk in the APK and verified their required tokens during both release and debug builds.
- Verified by 343 tests, source validation, four off-device UI goldens, the JavaScript WebView harness, secret scans, artifact inspection, exact installed-byte readback, session/project preservation, and the private Android WebView proof.
- Deferred AppFunctions, user-initiated transfer jobs, Jetpack WebMessageListener, and tailnet-wide posture/grant changes exactly as capability/API/admin-gated items in the matrix above; none is silently claimed as implemented.
8. Release artifacts carry package, version, signer, size, SHA-256, source tree, source commit, contract hash, and verification commands in a machine-readable manifest.

## Explicitly deferred, capability-gated work

- Android AppFunctions until the project intentionally migrates to target SDK 36+, compile SDK 37+, Kotlin/KSP/Jetpack, and an Android 16 verification device.
- UIDT jobs until the Android target/API migration is planned and tested against current foreground-service behavior.
- `addWebMessageListener` until Jetpack WebKit can be introduced without weakening the signed localhost-only WebView boundary.
- Tailscale posture/grant policy changes and GitHub repository-level immutability settings when the external account does not expose a verified authorized mutation route.

Deferral is not a claim that these capabilities are implemented. Capability discovery must report them as unavailable or preview-gated until independent runtime evidence says otherwise.
