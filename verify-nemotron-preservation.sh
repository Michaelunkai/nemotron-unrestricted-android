#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

# Verify an externally captured, credential-free preservation manifest without
# printing session contents, thread IDs, project paths, or credential values.
APP_HOME="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-/data/data/com.termux/files/usr/bin/python}"
MANIFEST=""
VERIFY_CWD=""
STATE_ROOT="$APP_HOME/runtime/.codex"

usage() {
  printf 'usage: %s --manifest <before.sha256> --cwd <manifest-working-directory> [--state-root <runtime/.codex>]\n' "$0"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --manifest) MANIFEST=${2:-}; shift 2 ;;
    --cwd) VERIFY_CWD=${2:-}; shift 2 ;;
    --state-root) STATE_ROOT=${2:-}; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) usage >&2; exit 64 ;;
  esac
done

[ -n "$MANIFEST" ] && [ -n "$VERIFY_CWD" ] || { usage >&2; exit 64; }
[ -f "$MANIFEST" ] && [ ! -L "$MANIFEST" ] || { printf 'PRESERVATION_MANIFEST_INVALID\n' >&2; exit 2; }
[ -d "$VERIFY_CWD" ] || { printf 'PRESERVATION_MANIFEST_CWD_INVALID\n' >&2; exit 2; }
[ -d "$STATE_ROOT" ] || { printf 'PRESERVATION_STATE_ROOT_INVALID\n' >&2; exit 2; }
MANIFEST="$(CDPATH= cd -- "$(dirname -- "$MANIFEST")" && pwd)/$(basename -- "$MANIFEST")"
VERIFY_CWD="$(CDPATH= cd -- "$VERIFY_CWD" && pwd)"
STATE_ROOT="$(CDPATH= cd -- "$STATE_ROOT" && pwd)"

if ! (cd "$VERIFY_CWD" && sha256sum -c --status "$MANIFEST") 2>/dev/null; then
  printf 'PRESERVATION_MANIFEST_MISMATCH\n' >&2
  exit 1
fi
entry_count=$(awk 'NF >= 2 && $1 !~ /^#/ { count += 1 } END { print count + 0 }' "$MANIFEST")
printf 'PRESERVATION_MANIFEST_OK entries=%s\n' "$entry_count"

"$PYTHON_BIN" - "$STATE_ROOT" <<'PY'
import hashlib
import json
import pathlib
import sqlite3
import sys
import urllib.parse

root = pathlib.Path(sys.argv[1])
session_directories = (root / "sessions", root / "archived_sessions")
workspace = root / "workspace"
thread_values = set()
project_values = set()
parse_errors = 0

def files_below(directory):
    if not directory.is_dir() or directory.is_symlink():
        return []
    return [path for path in directory.rglob("*") if path.is_file() and not path.is_symlink()]

def collect(value):
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).replace("_", "").lower()
            if normalized in {"threadid", "thread"} and isinstance(child, str) and child:
                thread_values.add(child)
            elif normalized in {"cwd", "project", "projectpath", "projectroot", "root"} and isinstance(child, str) and child:
                project_values.add(child)
            collect(child)
    elif isinstance(value, list):
        for child in value:
            collect(child)

session_files = []
for directory in session_directories:
    session_files.extend(files_below(directory))
jsonl_files = [path for path in session_files if path.suffix == ".jsonl"]
for path in jsonl_files:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                    if isinstance(row, dict) and row.get("type") == "session_meta":
                        payload = row.get("payload")
                        if isinstance(payload, dict):
                            session_id = payload.get("session_id") or payload.get("id")
                            if isinstance(session_id, str) and session_id:
                                thread_values.add(session_id)
                    collect(row)
                except json.JSONDecodeError:
                    parse_errors += 1
    except OSError:
        parse_errors += 1

sqlite_status = "absent"
database = root / "state_5.sqlite"
if database.is_file() and not database.is_symlink():
    try:
        uri = "file:" + urllib.parse.quote(str(database)) + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        sqlite_status = "read"
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        for (table,) in tables:
            escaped_table = str(table).replace('"', '""')
            columns = connection.execute(f'PRAGMA table_info("{escaped_table}")').fetchall()
            for column in columns:
                name = str(column[1])
                normalized = name.replace("_", "").lower()
                if normalized not in {"threadid", "thread", "cwd", "project", "projectpath", "projectroot", "root"}:
                    continue
                escaped_column = name.replace('"', '""')
                for (value,) in connection.execute(
                    f'SELECT "{escaped_column}" FROM "{escaped_table}" WHERE "{escaped_column}" IS NOT NULL'
                ):
                    if not isinstance(value, str) or not value:
                        continue
                    if normalized in {"threadid", "thread"}:
                        thread_values.add(value)
                    else:
                        project_values.add(value)
        connection.close()
    except sqlite3.Error:
        sqlite_status = "unreadable"

def fingerprint(values):
    if not values:
        return "-"
    return hashlib.sha256("\n".join(sorted(values)).encode("utf-8")).hexdigest()[:24]

print(
    "PRESERVATION_STATE_OK"
    f" session_files={len(session_files)}"
    f" session_jsonl={len(jsonl_files)}"
    f" workspace_files={len(files_below(workspace))}"
    f" unique_threads={len(thread_values)}"
    f" thread_fingerprint={fingerprint(thread_values)}"
    f" unique_project_roots={len(project_values)}"
    f" project_fingerprint={fingerprint(project_values)}"
    f" sqlite={sqlite_status}"
    f" parse_errors={parse_errors}"
)
PY
