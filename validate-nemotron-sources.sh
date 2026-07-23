#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

# Parse every project-authored executable source without producing bytecode or
# touching the isolated runtime. The Node harness is intentionally part of this
# gate because it validates the real overlay event/recovery contract, not only
# JavaScript grammar.
APP_HOME="${NEMOTRON_PROJECT_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)}"
PYTHON_BIN="${PYTHON_BIN:-/data/data/com.termux/files/usr/bin/python}"
NODE_BIN="${NODE_BIN:-node}"

test -x "$PYTHON_BIN" || { printf 'Python interpreter is unavailable.\n' >&2; exit 2; }
command -v "$NODE_BIN" >/dev/null || { printf 'Node.js is unavailable.\n' >&2; exit 2; }

"$PYTHON_BIN" - "$APP_HOME" <<'PY'
import os
import pathlib
import sys

root = pathlib.Path(sys.argv[1]).resolve()
excluded = {".git", "build", "build-tools", "dist", "runtime", "vendor", "workspace"}
sources = []
for directory, names, files in os.walk(root):
    path = pathlib.Path(directory)
    names[:] = sorted(name for name in names if name not in excluded)
    for name in sorted(files):
        candidate = path / name
        if candidate.is_symlink() or not candidate.is_file():
            continue
        try:
            first_line = candidate.open("rb").readline(256).decode("utf-8", "ignore")
        except OSError as error:
            raise SystemExit(f"Unable to read Python candidate {candidate}: {error}")
        if candidate.suffix == ".py" or (first_line.startswith("#!") and "python" in first_line.lower()):
            try:
                compile(candidate.read_text(encoding="utf-8"), str(candidate), "exec")
            except (OSError, SyntaxError) as error:
                raise SystemExit(f"Python syntax failed for {candidate}: {error}")
            sources.append(candidate.relative_to(root).as_posix())
print(f"NEMOTRON_PYTHON_SYNTAX_OK files={len(sources)}")
PY

shell_count=0
while IFS= read -r -d '' candidate; do
  first_line=$(head -n 1 "$candidate" || true)
  case "$first_line" in
    '#!'*bash*)
      bash -n "$candidate"
      shell_count=$((shell_count + 1))
      ;;
    '#!'*'/sh'*)
      sh -n "$candidate"
      shell_count=$((shell_count + 1))
      ;;
  esac
done < <(find "$APP_HOME" \
  \( -path "$APP_HOME/.git" -o -path "$APP_HOME/build" -o -path "$APP_HOME/build-tools" -o -path "$APP_HOME/dist" -o -path "$APP_HOME/runtime" -o -path "$APP_HOME/vendor" -o -path "$APP_HOME/workspace" \) -prune -o \
  -type f -print0)
printf 'NEMOTRON_SHELL_SYNTAX_OK files=%s\n' "$shell_count"

js_count=0
while IFS= read -r -d '' source; do
  "$NODE_BIN" --check "$source"
  js_count=$((js_count + 1))
done < <(find "$APP_HOME" \
  \( -path "$APP_HOME/.git" -o -path "$APP_HOME/build" -o -path "$APP_HOME/build-tools" -o -path "$APP_HOME/dist" -o -path "$APP_HOME/runtime" -o -path "$APP_HOME/vendor" -o -path "$APP_HOME/workspace" \) -prune -o \
  -type f -name '*.js' -print0)
printf 'NEMOTRON_JS_SYNTAX_OK files=%s\n' "$js_count"
"$PYTHON_BIN" "$APP_HOME/tools/patch-codexapp-ui.py" --check
"$PYTHON_BIN" "$APP_HOME/tools/render-offdevice-ui.py" --check
"$NODE_BIN" "$APP_HOME/tests/progress_overlay_harness.js"
"$NODE_BIN" "$APP_HOME/tests/gallery_frontend_harness.js"
printf 'NEMOTRON_SOURCE_VALIDATION_OK\n'
