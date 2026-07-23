#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

PROJECT_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
SOURCE_DIR="$PROJECT_ROOT/capabilities"
TARGET_DIR="$PROJECT_ROOT/runtime/.codex/skills"
mkdir -p "$TARGET_DIR"

while IFS= read -r -d '' cap; do
  relative=${cap#"$SOURCE_DIR"/}
  target="$TARGET_DIR/$relative"
  mkdir -p "$(dirname "$target")"
  if ! cmp -s "$cap" "$target" 2>/dev/null; then
    cp "$cap" "$target"
    printf 'Synced capability: %s\n' "$relative"
  fi
done < <(find "$SOURCE_DIR" -type f -print0 | sort -z)
printf 'CAPABILITY_SYNC_COMPLETE\n'
