#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

# This gate deliberately stops before Android installation. It proves the
# offline release surface and both preservation snapshots; the signer-pinned
# in-place install and device lifecycle checks remain explicit later phases.
APP_HOME="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-/data/data/com.termux/files/usr/bin/python}"
MANIFEST=""
MANIFEST_CWD=""
STATE_ROOT="$APP_HOME/runtime/.codex"
LOCAL_PRIVATE=0

usage() {
  printf 'usage: %s --manifest <before.sha256> --manifest-cwd <directory> [--state-root <runtime/.codex>] [--local-private]\n' "$0"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --manifest) MANIFEST=${2:-}; shift 2 ;;
    --manifest-cwd) MANIFEST_CWD=${2:-}; shift 2 ;;
    --state-root) STATE_ROOT=${2:-}; shift 2 ;;
    --local-private) LOCAL_PRIVATE=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) usage >&2; exit 64 ;;
  esac
done

[ -n "$MANIFEST" ] && [ -n "$MANIFEST_CWD" ] || { usage >&2; exit 64; }

verify_preservation() {
  "$APP_HOME/verify-nemotron-preservation.sh" \
    --manifest "$MANIFEST" \
    --cwd "$MANIFEST_CWD" \
    --state-root "$STATE_ROOT"
}

verify_preservation
"$APP_HOME/bootstrap-nemotron-runtime.sh"
"$APP_HOME/sync-nemotron-web.sh"
"$APP_HOME/validate-nemotron-sources.sh"
if [ "$LOCAL_PRIVATE" -eq 1 ]; then
  "$APP_HOME/scan-nemotron-secrets.py" --current-only
  printf 'LOCAL_PRIVATE_RELEASE_HISTORY_NOT_PUBLISHABLE\n'
else
  "$APP_HOME/scan-nemotron-secrets.py"
fi
"$PYTHON_BIN" -m unittest discover -s tests -v
"$APP_HOME/isolation-preflight.sh"
git -C "$APP_HOME" diff --check
staged_count=$(git -C "$APP_HOME" diff --cached --name-only | sed '/^$/d' | wc -l | tr -d ' ')
printf 'RELEASE_STAGED_FILES count=%s\n' "$staged_count"
if [ "$staged_count" -gt 0 ]; then
  git -C "$APP_HOME" diff --cached --name-only
fi
"$APP_HOME/build-nemotron-unrestricted.sh"

APK="$APP_HOME/dist/Nemotron-Unrestricted-1.0.0.apk"
test -s "$APK" && test -s "$APK.sha256"
(cd "$APP_HOME/dist" && sha256sum -c --status "$(basename "$APK.sha256")")
zipalign -c 4 "$APK"
verification=$(apksigner verify --verbose --print-certs "$APK")
printf '%s\n' "$verification" | grep -Fq 'Verified using v1 scheme (JAR signing): true'
printf '%s\n' "$verification" | grep -Fq 'Verified using v2 scheme (APK Signature Scheme v2): true'
printf '%s\n' "$verification" | grep -Fq 'Verified using v3 scheme (APK Signature Scheme v3): true'
[ -s "$APK.idsig" ] || { printf 'RELEASE_V4_SIDECAR_MISSING\n' >&2; exit 1; }
printf 'RELEASE_V4_SIDECAR_PRESENT verifier_confirmation_unavailable\n'
aapt dump badging "$APK" | grep -q "package: name='com.michaelovsky.nemotronunrestricted.isolated' versionCode='1' versionName='1.0.0'"
signer=$(printf '%s\n' "$verification" | awk -F': ' '/certificate SHA-256 digest:/ {print $NF; exit}')
printf '%s' "$signer" | grep -Eq '^[0-9a-f]{64}$' || { printf 'RELEASE_SIGNER_UNAVAILABLE\n' >&2; exit 1; }
verify_preservation
printf 'RELEASE_APK_OK sha256=%s signer_sha256=%s\n' "$(awk '{print $1}' "$APK.sha256")" "$signer"
printf 'NEMOTRON_RELEASE_GATE_OK\n'
