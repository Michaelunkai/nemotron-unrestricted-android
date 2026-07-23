#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

# Create only the non-secret, deterministic runtime files needed by local
# validation. Existing user-owned runtime state is intentionally never replaced.
APP_HOME="${NEMOTRON_PROJECT_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)}"
TEMPLATE_ROOT="$APP_HOME/runtime-template/.codex"
RUNTIME_ROOT="$APP_HOME/runtime/.codex"

test -d "$TEMPLATE_ROOT" || { printf 'Runtime template is missing.\n' >&2; exit 2; }
umask 077
mkdir -p "$RUNTIME_ROOT"

for name in config.toml webui-custom-providers.json; do
  source_file="$TEMPLATE_ROOT/$name"
  target_file="$RUNTIME_ROOT/$name"
  test -s "$source_file" || { printf 'Runtime template file is missing: %s\n' "$name" >&2; exit 2; }
  if [ ! -e "$target_file" ]; then
    cp "$source_file" "$target_file"
    chmod 600 "$target_file"
  fi
done

printf 'NEMOTRON_RUNTIME_BOOTSTRAP_OK\n'
