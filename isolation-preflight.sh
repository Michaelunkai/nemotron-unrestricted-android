#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

PROJECT_ROOT="/data/data/com.termux/files/home/nemotron-unrestricted-app"
PACKAGE="com.michaelovsky.nemotronunrestricted.isolated"
PYTHON_BIN="/data/data/com.termux/files/usr/bin/python"
DEFAULT_GUI_PORT=5903
DEFAULT_PROXY_PORT=18774
DEFAULT_SUPERVISOR_PORT=18775
PORT_STATE_FILE="$PROJECT_ROOT/runtime/.codex/supervisor/ports.env"
WEB_SOURCE="$PROJECT_ROOT/web/nemotron-autonomy-progress.js"
WEB_TARGET="$PROJECT_ROOT/vendor/codexapp-native-npm/node_modules/codexapp/dist/nemotron-autonomy-progress.js"
WEB_INDEX="$PROJECT_ROOT/vendor/codexapp-native-npm/node_modules/codexapp/dist/index.html"
HTML_PREMOUNT_OVERLAY_TAG='<script src="/nemotron-autonomy-progress.js'
TEMPLATE_CONFIG="$PROJECT_ROOT/runtime-template/.codex/config.toml"
LIVE_CONFIG="$PROJECT_ROOT/runtime/.codex/config.toml"
PROXY_SOURCE_HASH=$(sha256sum "$PROJECT_ROOT/nemotron_unrestricted_proxy.py" | awk '{print $1}')
SUPERVISOR_SOURCE_HASH=$(sha256sum "$PROJECT_ROOT/nemotron_session_supervisor.py" | awk '{print $1}')

"$PROJECT_ROOT/bootstrap-nemotron-runtime.sh"

port_is_available() {
  "$PYTHON_BIN" - "$1" <<'PY'
import socket
import sys

try:
    port = int(sys.argv[1])
    if not 1 <= port <= 65535:
        raise ValueError("port outside valid range")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", port))
except (OSError, ValueError):
    sys.exit(1)
PY
}

endpoint_is_ours() {
  "$PYTHON_BIN" - "$1" "$2" "$PROXY_SOURCE_HASH" "$SUPERVISOR_SOURCE_HASH" <<'PY'
import json
import sys
import urllib.request

label, raw_port, proxy_hash, supervisor_hash = sys.argv[1:]
port = int(raw_port)
path = "/codex-api/meta/methods" if label == "GUI" else "/vault-health" if label == "proxy" else "/health"
try:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=1.5) as response:
        data = json.load(response)
except Exception:
    raise SystemExit(1)
if label == "GUI":
    methods = data.get("data") if isinstance(data, dict) else None
    ok = isinstance(methods, list) and "config/read" in methods and "thread/start" in methods
elif label == "proxy":
    ok = data.get("app") == "nemotron-unrestricted" and data.get("status") == "ok" and data.get("sourceSha256") == proxy_hash
else:
    ok = data.get("app") == "nemotron-unrestricted" and data.get("status") == "ok" and data.get("sourceSha256") == supervisor_hash
raise SystemExit(0 if ok else 1)
PY
}

select_port() {
  preferred="$1"
  shift
  candidate="$preferred"
  upper_bound=$((preferred + 100))
  while [ "$candidate" -le "$upper_bound" ]; do
    selected_elsewhere=0
    for selected in "$@"; do
      if [ "$candidate" = "$selected" ]; then selected_elsewhere=1; break; fi
    done
    if [ "$selected_elsewhere" -eq 0 ] && port_is_available "$candidate"; then
      printf '%s\n' "$candidate"
      return 0
    fi
    candidate=$((candidate + 1))
  done
  return 1
}

resolve_port() {
  requested="$1"
  preferred="$2"
  label="$3"
  shift 3
  if [ -n "$requested" ]; then
    if ! port_is_available "$requested"; then
      if endpoint_is_ours "$label" "$requested"; then
        printf '%s\n' "$requested"
        return 0
      fi
      printf 'ERROR: requested %s port %s already in use by an unverified owner or invalid\n' "$label" "$requested" >&2
      return 1
    fi
    printf '%s\n' "$requested"
    return 0
  fi
  select_port "$preferred" "$@" || { printf 'ERROR: no free %s port near %s\n' "$label" "$preferred" >&2; return 1; }
}

# A standalone preflight must validate the ports already owned by a live
# Nemotron runtime instead of treating that runtime as a collision and
# reporting a second, unused port set.  Parse only decimal assignments; never
# source the state file because it is runtime data rather than shell code.
if [ -r "$PORT_STATE_FILE" ]; then
  SAVED_GUI_PORT=$(sed -n 's/^NEMOTRON_GUI_PORT=\([0-9][0-9]*\)$/\1/p' "$PORT_STATE_FILE" | tail -n 1)
  SAVED_PROXY_PORT=$(sed -n 's/^NEMOTRON_PROXY_PORT=\([0-9][0-9]*\)$/\1/p' "$PORT_STATE_FILE" | tail -n 1)
  SAVED_SUPERVISOR_PORT=$(sed -n 's/^NEMOTRON_SUPERVISOR_PORT=\([0-9][0-9]*\)$/\1/p' "$PORT_STATE_FILE" | tail -n 1)
  NEMOTRON_GUI_PORT=${NEMOTRON_GUI_PORT:-$SAVED_GUI_PORT}
  NEMOTRON_PROXY_PORT=${NEMOTRON_PROXY_PORT:-$SAVED_PROXY_PORT}
  NEMOTRON_SUPERVISOR_PORT=${NEMOTRON_SUPERVISOR_PORT:-$SAVED_SUPERVISOR_PORT}
fi

GUI_PORT=$(resolve_port "${NEMOTRON_GUI_PORT:-}" "$DEFAULT_GUI_PORT" GUI)
PROXY_PORT=$(resolve_port "${NEMOTRON_PROXY_PORT:-}" "$DEFAULT_PROXY_PORT" proxy "$GUI_PORT")
SUPERVISOR_PORT=$(resolve_port "${NEMOTRON_SUPERVISOR_PORT:-}" "$DEFAULT_SUPERVISOR_PORT" supervisor "$GUI_PORT" "$PROXY_PORT")
if [ "$GUI_PORT" = "$PROXY_PORT" ] || [ "$GUI_PORT" = "$SUPERVISOR_PORT" ] || [ "$PROXY_PORT" = "$SUPERVISOR_PORT" ]; then
  printf 'ERROR: selected isolated ports must be distinct\n' >&2
  exit 1
fi

test -s "$WEB_SOURCE" || { printf 'ERROR: Nemotron web overlay source is missing\n' >&2; exit 1; }
test -s "$WEB_TARGET" || { printf 'ERROR: Nemotron web overlay deployment is missing\n' >&2; exit 1; }
cmp -s "$WEB_SOURCE" "$WEB_TARGET" || { printf 'ERROR: Nemotron web overlay deployment is stale\n' >&2; exit 1; }
! grep -Fq "$HTML_PREMOUNT_OVERLAY_TAG" "$WEB_INDEX" || { printf 'ERROR: pre-mount Nemotron overlay can race Vue startup\n' >&2; exit 1; }
grep -Fq '<meta name="apple-mobile-web-app-title" content="Nemotron Unrestricted" />' "$WEB_INDEX" || { printf 'ERROR: Nemotron web title is not isolated\n' >&2; exit 1; }
grep -Fq '<title>Nemotron Unrestricted</title>' "$WEB_INDEX" || { printf 'ERROR: Nemotron document title is not isolated\n' >&2; exit 1; }
if grep -Fq '<script src="/nvidia-autonomy-progress.js"></script>' "$WEB_INDEX"; then
  printf 'ERROR: NVIDIA web overlay leaked into Nemotron\n' >&2
  exit 1
fi
test ! -e "$PROJECT_ROOT/nemotron_isolated_proxy.py" || { printf 'ERROR: obsolete NVIDIA proxy source is present\n' >&2; exit 1; }
test ! -e "$PROJECT_ROOT/vendor/codexapp-native-npm/node_modules/codexapp/dist/nvidia-autonomy-progress.js" \
  || { printf 'ERROR: obsolete NVIDIA web overlay is present\n' >&2; exit 1; }

for config in "$TEMPLATE_CONFIG" "$LIVE_CONFIG"; do
  test -s "$config" || { printf 'ERROR: runtime configuration is missing: %s\n' "$config" >&2; exit 1; }
  if grep -Eq '\[projects\."/data/data/com\.termux/files/home/(codex-subscription-isolated-app|nvidia-isolated-app|com\.michaelovsky\.nemotronunrestricted\.isolated)"\]' "$config"; then
    printf 'ERROR: sibling or stale project trust leaked into %s\n' "$config" >&2
    exit 1
  fi
done

for executable in codex-android codex-download codex-install codex-package codex-pm codex-shizuku codex-uninstall rish; do
  test -x "$PROJECT_ROOT/bin/$executable" || { printf 'ERROR: guarded command is missing: %s\n' "$executable" >&2; exit 1; }
done

credential_file="$PROJECT_ROOT/runtime/.codex/openrouter.env"
if [ -e "$credential_file" ]; then
  credential_mode=$(stat -c '%a' "$credential_file")
  [ "$credential_mode" = 600 ] || { printf 'ERROR: OpenRouter credential file mode must be 600\n' >&2; exit 1; }
fi

if ! package_inventory=$("$PROJECT_ROOT/bin/codex-android" packages 2>/dev/null); then
  printf 'ERROR: isolated Shizuku package discovery failed\n' >&2
  exit 1
fi
if ! PACKAGE_INVENTORY="$package_inventory" "$PYTHON_BIN" - \
    com.michaelovsky.codexapplauncher \
    com.michaelovsky.codexsubscription.isolated \
    com.michaelovsky.codexnvidia.isolated <<'PY'
import json
import os
import sys

protected = sys.argv[1:]
try:
    payload = json.loads(os.environ["PACKAGE_INVENTORY"])
except (KeyError, json.JSONDecodeError):
    print("ERROR: isolated package inventory receipt is invalid", file=sys.stderr)
    raise SystemExit(1)
packages = payload.get("packages")
if payload.get("ok") is not True or payload.get("verified") is not True or not isinstance(packages, list):
    print("ERROR: isolated package inventory is not verified", file=sys.stderr)
    raise SystemExit(1)
if payload.get("count") != len(packages) or any(not isinstance(package, str) for package in packages):
    print("ERROR: isolated package inventory is inconsistent", file=sys.stderr)
    raise SystemExit(1)
installed = set(packages)
for package in protected:
    if package in installed:
        print(f"Protected package {package} exists (OK)")
    else:
        print(f"Warning: protected package {package} not installed", file=sys.stderr)
PY
then
  exit 1
fi

for port in 5900 5901 5902 18768 18769 18770 18771; do
  if ! port_is_available "$port"; then
    printf 'Protected port %s in use (OK)\n' "$port"
  fi
done

for spec in "GUI:$GUI_PORT" "proxy:$PROXY_PORT" "supervisor:$SUPERVISOR_PORT"; do
  label=${spec%%:*}
  port=${spec#*:}
  if ! port_is_available "$port"; then
    if endpoint_is_ours "$label" "$port"; then
      printf 'Nemotron-owned %s port %s already healthy (OK)\n' "$label" "$port"
    else
      printf 'ERROR: our %s port %s already in use by an unverified owner\n' "$label" "$port" >&2
      exit 1
    fi
  fi
done

printf 'NEMOTRON_PORTS gui=%s proxy=%s supervisor=%s\n' "$GUI_PORT" "$PROXY_PORT" "$SUPERVISOR_PORT"
printf 'ISOLATION_PREFLIGHT_OK\n'
