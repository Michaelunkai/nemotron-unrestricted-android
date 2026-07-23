#!/data/data/com.termux/files/usr/bin/python
"""Capture a private, credential-excluding preservation manifest for an in-place update."""

import argparse
import hashlib
import os
import pathlib
import sys


APP_ROOT = pathlib.Path(__file__).resolve().parent


def under(root, candidate):
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def selected_files(project_root, state_root, *, include_sqlite=False):
    candidates = []
    for relative in ("sessions", "archived_sessions", "workspace"):
        directory = state_root / relative
        if directory.is_dir() and not directory.is_symlink():
            candidates.extend(path for path in directory.rglob("*") if path.is_file() and not path.is_symlink())
    if include_sqlite:
        for name in ("state_5.sqlite", "state_5.sqlite-wal", "state_5.sqlite-shm"):
            path = state_root / name
            if path.is_file() and not path.is_symlink():
                candidates.append(path)
    return sorted(set(candidates), key=lambda path: path.relative_to(project_root).as_posix())


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser(description="Create a credential-excluding state preservation manifest.")
    parser.add_argument("--output", type=pathlib.Path, required=True, help="new manifest path inside this project")
    parser.add_argument("--state-root", type=pathlib.Path, default=APP_ROOT / "runtime/.codex")
    parser.add_argument(
        "--include-sqlite",
        action="store_true",
        help="also hash mutable SQLite/WAL files; disabled by default for a live runtime",
    )
    arguments = parser.parse_args()
    project_root = APP_ROOT.resolve()
    state_root = arguments.state_root.resolve()
    output = arguments.output.resolve()
    if not state_root.is_dir() or state_root.is_symlink():
        raise SystemExit("PRESERVATION_CAPTURE_STATE_ROOT_INVALID")
    if not under(project_root, state_root):
        raise SystemExit("PRESERVATION_CAPTURE_STATE_ROOT_OUTSIDE_PROJECT")
    if not under(project_root, output):
        raise SystemExit("PRESERVATION_CAPTURE_OUTPUT_OUTSIDE_PROJECT")
    if output.exists() or output.is_symlink():
        raise SystemExit("PRESERVATION_CAPTURE_OUTPUT_EXISTS")
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    files = selected_files(project_root, state_root, include_sqlite=arguments.include_sqlite)
    temporary = output.with_name(output.name + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            for path in files:
                handle.write(f"{digest(path)}  {path.relative_to(project_root).as_posix()}\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
    except Exception:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise
    print(f"PRESERVATION_CAPTURE_OK entries={len(files)}")


if __name__ == "__main__":
    main()
