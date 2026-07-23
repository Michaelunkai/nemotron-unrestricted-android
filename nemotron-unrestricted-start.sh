#!/data/data/com.termux/files/usr/bin/bash
set -eu
umask 077

TERMUX_HOME="/data/data/com.termux/files/home"
APP_HOME="$TERMUX_HOME/nemotron-unrestricted-app"
ISOLATED_CODEX_ROOT="$APP_HOME/runtime/.codex"
ISOLATED_WORKSPACE="$APP_HOME/workspace"
ISOLATED_HOME="$APP_HOME/runtime/home"
export PATH="$APP_HOME/bin:/data/data/com.termux/files/usr/bin:$TERMUX_HOME/.local/bin:$PATH"
SYSTEM_CA_BUNDLE="/data/data/com.termux/files/usr/etc/tls/cert.pem"
if [ -f "$SYSTEM_CA_BUNDLE" ] && [ ! -L "$SYSTEM_CA_BUNDLE" ]; then
  export SSL_CERT_FILE="$SYSTEM_CA_BUNDLE"
  export REQUESTS_CA_BUNDLE="$SYSTEM_CA_BUNDLE"
  export CURL_CA_BUNDLE="$SYSTEM_CA_BUNDLE"
  export NODE_EXTRA_CA_CERTS="$SYSTEM_CA_BUNDLE"
fi
DEFAULT_GUI_PORT=5903
DEFAULT_PROXY_PORT=18774
DEFAULT_SUPERVISOR_PORT=18775
LOG_DIR="$ISOLATED_CODEX_ROOT/logs"
LOCK_DIR="$ISOLATED_CODEX_ROOT/locks"
SUPERVISOR_DIR="$ISOLATED_CODEX_ROOT/supervisor"
PORT_STATE_FILE="$SUPERVISOR_DIR/ports.env"
PYTHON_BIN="/data/data/com.termux/files/usr/bin/python"
PROXY_SOURCE="$APP_HOME/nemotron_unrestricted_proxy.py"
SUPERVISOR_SOURCE="$APP_HOME/nemotron_session_supervisor.py"
PROXY_HASH_FILE="$SUPERVISOR_DIR/nemotron-proxy-source.sha256"
SUPERVISOR_HASH_FILE="$SUPERVISOR_DIR/nemotron-supervisor-source.sha256"
DOLPHIN_X1_PORT=18780
WINDOWS_GATEWAY_CONFIG="/data/data/com.termux/files/home/.codex/vault/windows-gateway.json"

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

stop_python_script() {
  target="$1"
  for process in /proc/[0-9]*; do
    [ -r "$process/cmdline" ] || continue
    arguments=$({ tr '\000' '\n' < "$process/cmdline"; } 2>/dev/null || true)
    [ -n "$arguments" ] || continue
    executable=$(printf '%s\n' "$arguments" | sed -n '1p')
    script=$(printf '%s\n' "$arguments" | sed -n '2p')
    if [ "$executable" = "$PYTHON_BIN" ] && [ "$script" = "$target" ] \
      && process_is_owned_session_leader "${process##*/}"; then
      kill -- "-${process##*/}" 2>/dev/null || true
    fi
  done
}

process_is_owned_session_leader() {
  pid="$1"
  [ -r "/proc/$pid/environ" ] || return 1
  identity=$(ps -o uid=,pgid=,sid= -p "$pid" 2>/dev/null) || return 1
  set -- $identity
  [ "$#" -eq 3 ] || return 1
  [ "$1" = "$(id -u)" ] && [ "$2" = "$pid" ] && [ "$3" = "$pid" ] || return 1
  environment=$({ tr '\000' '\n' < "/proc/$pid/environ"; } 2>/dev/null || true)
  printf '%s\n' "$environment" | grep -Fqx "HOME=$ISOLATED_HOME" \
    && printf '%s\n' "$environment" | grep -Fqx "CODEX_HOME=$ISOLATED_CODEX_ROOT" \
    && printf '%s\n' "$environment" | grep -Fqx "CODEX_RUNTIME_ROOT=$ISOLATED_CODEX_ROOT"
}

stop_gui_server() {
  for process in /proc/[0-9]*; do
    [ -r "$process/cmdline" ] || continue
    arguments=$({ tr '\000' '\n' < "$process/cmdline"; } 2>/dev/null || true)
    [ -n "$arguments" ] || continue
    executable=$(printf '%s\n' "$arguments" | sed -n '1p')
    script=$(printf '%s\n' "$arguments" | sed -n '2p')
    workspace=$(printf '%s\n' "$arguments" | sed -n '3p')
    if [ "$executable" = "/data/data/com.termux/files/usr/bin/node" ] \
      && [ "$script" = "$APP_HOME/vendor/codexapp-native-npm/node_modules/codexapp/dist-cli/index.js" ] \
      && [ "$workspace" = "$ISOLATED_WORKSPACE" ] \
      && process_is_owned_session_leader "${process##*/}"; then
      kill -- "-${process##*/}" 2>/dev/null || true
    fi
  done
}

wait_for_ports_to_release() {
  for _ in 1 2 3 4 5; do
    if port_is_available "$DEFAULT_GUI_PORT" \
      && port_is_available "$DEFAULT_PROXY_PORT" \
      && port_is_available "$DEFAULT_SUPERVISOR_PORT"; then
      return 0
    fi
    sleep 1
  done
}

write_provider_base_url() {
  "$PYTHON_BIN" - "$ISOLATED_CODEX_ROOT/webui-custom-providers.json" "$PROXY_PORT" <<'PY'
import json
import os
import pathlib
import sys

target = pathlib.Path(sys.argv[1])
port = int(sys.argv[2])
data = json.loads(target.read_text(encoding="utf-8"))
data["customBaseUrl"] = f"http://127.0.0.1:{port}/v1"
temporary = target.with_name(target.name + ".tmp")
temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
os.replace(temporary, target)
PY
}

provider_file_is_current() {
  "$PYTHON_BIN" - "$ISOLATED_CODEX_ROOT/webui-custom-providers.json" "$1" <<'PY'
import json
import pathlib
import sys

target = pathlib.Path(sys.argv[1])
expected = f"http://127.0.0.1:{int(sys.argv[2])}/v1"
try:
    data = json.loads(target.read_text(encoding="utf-8"))
    valid = (
        isinstance(data, dict)
        and data.get("enabled") is True
        and data.get("provider") == "custom"
        and data.get("customKey") is True
        and data.get("wireApi") == "chat"
        and data.get("customBaseUrl") == expected
    )
except Exception:
    valid = False
sys.exit(0 if valid else 1)
PY
}

ensure_private_credential_file() {
  "$PYTHON_BIN" - "$OPENROUTER_ENV_FILE" <<'PY'
import os
import pathlib
import stat
import sys

path = pathlib.Path(sys.argv[1])
template = (
    "# Add your OpenRouter API key here (https://openrouter.ai/keys)\n"
    "# Set OPENROUTER_API_KEY=<YOUR_OPENROUTER_API_KEY> in this private file.\n"
).encode("utf-8")
flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
if hasattr(os, "O_NOFOLLOW"):
    flags |= os.O_NOFOLLOW
try:
    descriptor = os.open(path, flags, 0o600)
except FileExistsError:
    descriptor = None
else:
    try:
        view = memoryview(template)
        while view:
            written = os.write(descriptor, view)
            if written < 1:
                raise OSError("credential template write failed")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)

flags = os.O_RDONLY
if hasattr(os, "O_NOFOLLOW"):
    flags |= os.O_NOFOLLOW
descriptor = os.open(path, flags)
try:
    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid():
        raise OSError("credential file identity is unsafe")
    os.fchmod(descriptor, 0o600)
finally:
    os.close(descriptor)
PY
}

valid_port() {
  case "$1" in
    ''|*[!0-9]*) return 1 ;;
  esac
  [ "$1" -ge 1 ] && [ "$1" -le 65535 ]
}

gui_is_ours() {
  "$PYTHON_BIN" - "$1" <<'PY'
import json
import sys
import urllib.request

port = int(sys.argv[1])
request = urllib.request.Request(
    f"http://127.0.0.1:{port}/codex-api/rpc",
    data=json.dumps({"method": "config/read", "params": {}}).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(request, timeout=2) as response:
        payload = json.load(response)
    config = payload["result"]["config"]
    valid = (
        isinstance(config.get("model"), str)
        and bool(config.get("model"))
        and config.get("model_provider") == "custom_endpoint"
        and config.get("approval_policy") == "never"
        and config.get("sandbox_mode") == "danger-full-access"
        and "isolated Nemotron Autonomy runtime using OpenRouter" in config.get("developer_instructions", "")
    )
except Exception:
    valid = False
sys.exit(0 if valid else 1)
PY
}

proxy_is_ours() {
  "$PYTHON_BIN" - "$1" "$2" "$3" "$4" "$5" <<'PY'
import hashlib
import json
import pathlib
import re
import sys
import urllib.request

port = int(sys.argv[1])
gui_port = int(sys.argv[2])
supervisor_port = int(sys.argv[3])
expected_hash = sys.argv[4]
expected_supervisor_hash = sys.argv[5]
capability_contract = pathlib.Path(
    "/data/data/com.termux/files/home/nemotron-unrestricted-app/capabilities/NEMOTRON_AGENT_CONTRACT.md"
)
capability_matrix = capability_contract.with_name("capability-matrix.json")
expected_capability_hash = hashlib.sha256(
    capability_contract.read_bytes() + b"\0" + capability_matrix.read_bytes()
).hexdigest()
expected_base_url = f"http://127.0.0.1:{port}/v1"
try:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/vault-health", timeout=2) as response:
        health = json.load(response)
    valid = (
        health.get("status") == "ok"
        and health.get("app") == "nemotron-unrestricted"
        and health.get("provider") == "OpenRouter"
        and health.get("model") == "nousresearch/hermes-4-405b"
        and health.get("proxyPort") == port
        and health.get("port") == port
        and health.get("guiPort") == gui_port
        and health.get("supervisorPort") == supervisor_port
        and health.get("providerBaseUrl") == expected_base_url
        and health.get("effectiveBaseUrl") == expected_base_url
        and health.get("sourceHash") == expected_hash
        and health.get("sourceSha256") == expected_hash
        and health.get("supervisorSourceHash") == expected_supervisor_hash
        and health.get("capabilityContractSha256") == expected_capability_hash
        and health.get("capabilityContractAppliesToEveryModel") is True
        and health.get("englishProgressRequired") is True
        and isinstance(health.get("credentialConfigured"), bool)
        and isinstance(health.get("credentialSourceFingerprint"), str)
        and re.fullmatch(r"[0-9a-f]{24}", health["credentialSourceFingerprint"]) is not None
    )
except Exception:
    valid = False
sys.exit(0 if valid else 1)
PY
}

supervisor_is_ours() {
  "$PYTHON_BIN" - "$1" "$2" <<'PY'
import json
import sys
import urllib.request

port = int(sys.argv[1])
expected_hash = sys.argv[2]
try:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as response:
        health = json.load(response)
    valid = (
        health.get("status") == "ok"
        and health.get("app") == "nemotron-unrestricted"
        and health.get("port") == port
        and health.get("sourceSha256") == expected_hash
    )
except Exception:
    valid = False
sys.exit(0 if valid else 1)
PY
}

healthy_existing_runtime() {
  stored_gui="$1"
  stored_proxy="$2"
  stored_supervisor="$3"
  proxy_source_hash=$(sha256sum "$PROXY_SOURCE" | awk '{print $1}')
  supervisor_source_hash=$(sha256sum "$SUPERVISOR_SOURCE" | awk '{print $1}')
  provider_file_is_current "$stored_proxy" \
    && gui_is_ours "$stored_gui" \
    && proxy_is_ours "$stored_proxy" "$stored_gui" "$stored_supervisor" "$proxy_source_hash" "$supervisor_source_hash" \
    && supervisor_is_ours "$stored_supervisor" "$supervisor_source_hash" \
    && [ -s "$PROXY_HASH_FILE" ] \
    && [ "$(sed -n '1p' "$PROXY_HASH_FILE")" = "$proxy_source_hash" ] \
    && [ -s "$SUPERVISOR_HASH_FILE" ] \
    && [ "$(sed -n '1p' "$SUPERVISOR_HASH_FILE")" = "$supervisor_source_hash" ]
}

refresh_runtime_capabilities() {
  "$APP_HOME/sync-capabilities.sh" >> "$LOG_DIR/capability-sync.log" 2>&1
  cp "$APP_HOME/capabilities/NEMOTRON_AGENT_CONTRACT.md" "$ISOLATED_HOME/AGENTS.md"
}

resolve_dolphin_x1_base_url() {
  "$PYTHON_BIN" - "$WINDOWS_GATEWAY_CONFIG" "$DOLPHIN_X1_PORT" <<'PY'
import ipaddress
import json
import pathlib
import sys

try:
    value = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    host = str(value.get("host", "")).strip()
    address = ipaddress.ip_address(host)
    if address not in ipaddress.ip_network("100.64.0.0/10"):
        raise ValueError("not a Tailscale CGNAT address")
    port = int(sys.argv[2])
    if not 1 <= port <= 65535:
        raise ValueError("port")
    print(f"http://{host}:{port}/v1")
except (OSError, ValueError, TypeError, json.JSONDecodeError):
    pass
PY
}

mkdir -p "$ISOLATED_CODEX_ROOT/vault" "$ISOLATED_CODEX_ROOT/skills" "$ISOLATED_CODEX_ROOT/memories" "$ISOLATED_CODEX_ROOT/sessions" "$LOG_DIR" "$LOCK_DIR" "$SUPERVISOR_DIR" "$ISOLATED_WORKSPACE" "$ISOLATED_HOME"
OPENROUTER_ENV_FILE="$ISOLATED_CODEX_ROOT/openrouter.env"
ensure_private_credential_file

exec 9>"$LOCK_DIR/runtime-start.lock"
if ! flock -n 9; then exit 0; fi

# A foreground-service resume can request a launch while the isolated runtime is
# already ready. Reuse its recorded ports instead of tearing down healthy work.
if [ -r "$PORT_STATE_FILE" ]; then
  stored_gui=$(sed -n 's/^NEMOTRON_GUI_PORT=//p' "$PORT_STATE_FILE" | head -n 1)
  stored_proxy=$(sed -n 's/^NEMOTRON_PROXY_PORT=//p' "$PORT_STATE_FILE" | head -n 1)
  stored_supervisor=$(sed -n 's/^NEMOTRON_SUPERVISOR_PORT=//p' "$PORT_STATE_FILE" | head -n 1)
  if valid_port "$stored_gui" && valid_port "$stored_proxy" && valid_port "$stored_supervisor" \
    && [ "$stored_gui" != "$stored_proxy" ] && [ "$stored_gui" != "$stored_supervisor" ] && [ "$stored_proxy" != "$stored_supervisor" ] \
    && healthy_existing_runtime "$stored_gui" "$stored_proxy" "$stored_supervisor"; then
    refresh_runtime_capabilities
    exit 0
  fi
fi

# These are the only processes the launcher owns. Stopping them before choosing
# ports lets a restart reuse the preferred isolated addresses when possible.
stop_python_script "$SUPERVISOR_SOURCE"
stop_python_script "$PROXY_SOURCE"
stop_gui_server
wait_for_ports_to_release || true

PORT=$(select_port "$DEFAULT_GUI_PORT") || { printf 'no free isolated GUI port\n' >> "$LOG_DIR/startup-error.log"; exit 69; }
PROXY_PORT=$(select_port "$DEFAULT_PROXY_PORT" "$PORT") || { printf 'no free isolated proxy port\n' >> "$LOG_DIR/startup-error.log"; exit 69; }
SUPERVISOR_PORT=$(select_port "$DEFAULT_SUPERVISOR_PORT" "$PORT" "$PROXY_PORT") || { printf 'no free isolated supervisor port\n' >> "$LOG_DIR/startup-error.log"; exit 69; }
export NEMOTRON_GUI_PORT="$PORT" NEMOTRON_PROXY_PORT="$PROXY_PORT" NEMOTRON_SUPERVISOR_PORT="$SUPERVISOR_PORT"
DOLPHIN_X1_BASE_URL=$(resolve_dolphin_x1_base_url)
export DOLPHIN_X1_BASE_URL

"$APP_HOME/sync-nemotron-web.sh"
refresh_runtime_capabilities
if [ ! -f "$ISOLATED_CODEX_ROOT/config.toml" ]; then cp "$APP_HOME/runtime-template/.codex/config.toml" "$ISOLATED_CODEX_ROOT/config.toml"; fi
if [ ! -f "$ISOLATED_CODEX_ROOT/webui-custom-providers.json" ]; then cp "$APP_HOME/runtime-template/.codex/webui-custom-providers.json" "$ISOLATED_CODEX_ROOT/webui-custom-providers.json"; fi
write_provider_base_url
"$APP_HOME/isolation-preflight.sh"

port_state_tmp=$(mktemp "$SUPERVISOR_DIR/ports.env.XXXXXX")
printf 'NEMOTRON_GUI_PORT=%s\nNEMOTRON_PROXY_PORT=%s\nNEMOTRON_SUPERVISOR_PORT=%s\n' "$PORT" "$PROXY_PORT" "$SUPERVISOR_PORT" > "$port_state_tmp"
mv "$port_state_tmp" "$PORT_STATE_FILE"

setsid -f env HOME="$ISOLATED_HOME" CODEX_HOME="$ISOLATED_CODEX_ROOT" CODEX_RUNTIME_ROOT="$ISOLATED_CODEX_ROOT" NEMOTRON_GUI_PORT="$PORT" NEMOTRON_SUPERVISOR_PORT="$SUPERVISOR_PORT" "$PYTHON_BIN" "$SUPERVISOR_SOURCE" >> "$LOG_DIR/session-supervisor.log" 2>&1 9>&-
supervisor_source_hash=$(sha256sum "$SUPERVISOR_SOURCE" | awk '{print $1}')
supervisor_ready=0
for _ in 1 2 3 4 5 6 7 8 9 10; do
    if supervisor_is_ours "$SUPERVISOR_PORT" "$supervisor_source_hash"; then supervisor_ready=1; break; fi
  sleep 1
done
if [ "$supervisor_ready" -ne 1 ]; then printf 'isolated Nemotron supervisor unavailable\n' >> "$LOG_DIR/startup-error.log"; exit 71; fi
printf '%s\n' "$supervisor_source_hash" > "$SUPERVISOR_HASH_FILE"

proxy_source_hash=$(sha256sum "$PROXY_SOURCE" | awk '{print $1}')
setsid -f env HOME="$ISOLATED_HOME" CODEX_HOME="$ISOLATED_CODEX_ROOT" CODEX_RUNTIME_ROOT="$ISOLATED_CODEX_ROOT" NEMOTRON_GUI_PORT="$PORT" NEMOTRON_PROXY_PORT="$PROXY_PORT" NEMOTRON_SUPERVISOR_PORT="$SUPERVISOR_PORT" DOLPHIN_X1_BASE_URL="$DOLPHIN_X1_BASE_URL" "$PYTHON_BIN" "$PROXY_SOURCE" >> "$LOG_DIR/nemotron-proxy.log" 2>&1 9>&-
proxy_ready=0
for _ in 1 2 3 4 5 6 7 8 9 10; do
    if proxy_is_ours "$PROXY_PORT" "$PORT" "$SUPERVISOR_PORT" "$proxy_source_hash" "$supervisor_source_hash"; then proxy_ready=1; break; fi
  sleep 1
done
if [ "$proxy_ready" -ne 1 ]; then printf 'isolated Nemotron proxy unavailable\n' >> "$LOG_DIR/startup-error.log"; exit 70; fi
printf '%s\n' "$proxy_source_hash" > "$PROXY_HASH_FILE"

setsid -f env HOME="$ISOLATED_HOME" CODEX_HOME="$ISOLATED_CODEX_ROOT" CODEX_RUNTIME_ROOT="$ISOLATED_CODEX_ROOT" CODEXAPP_GUI_OWNER_MODE="nemotron-unrestricted" /data/data/com.termux/files/usr/bin/node "$APP_HOME/vendor/codexapp-native-npm/node_modules/codexapp/dist-cli/index.js" "$ISOLATED_WORKSPACE" -p "$PORT" --no-open --no-login --no-tunnel --approval-policy never --sandbox-mode danger-full-access >> "$LOG_DIR/codex-web.log" 2>&1 9>&-
gui_ready=0
for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
  if gui_is_ours "$PORT"; then gui_ready=1; break; fi
  sleep 1
done
if [ "$gui_ready" -ne 1 ]; then
  printf 'isolated Nemotron GUI failed ownership verification on port %s\n' "$PORT" >> "$LOG_DIR/startup-error.log"
  exit 72
fi
