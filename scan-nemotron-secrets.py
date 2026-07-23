#!/data/data/com.termux/files/usr/bin/python
"""Fail-closed, redacted secret scanning for the Nemotron release tree.

The scanner intentionally excludes the ignored live runtime, signing material, build
scratch, and vendored third-party payload. It scans authored release sources in the
working tree and every reachable Git revision, reporting only a rule and location.
No matched value is ever printed.
"""

import argparse
import pathlib
import re
import subprocess
import sys
import zipfile


SCRIPT_ROOT = pathlib.Path(__file__).resolve().parent
EXCLUDED_PREFIXES = (
    ".git/",
    "build/",
    "build-tools/",
    "dist/",
    "runtime/",
    "vendor/",
    "workspace/",
)
MAX_SOURCE_FILE_BYTES = 32 * 1024 * 1024

HARD_PATTERNS = (
    ("OpenRouter API key", re.compile(rb"\bsk-or-v1-[A-Za-z0-9_-]{20,}\b")),
    ("OpenAI API key", re.compile(rb"\bsk-(?!or-v1-)[A-Za-z0-9_-]{20,}\b")),
    ("GitHub token", re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("AWS access key", re.compile(rb"\b(?:AKIA|ASIA|A3T[A-Z])[A-Z0-9]{16}\b")),
    ("Slack token", re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("private key block", re.compile(rb"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----")),
)
ASSIGNMENT_PATTERN = re.compile(
    rb"(?m)^[ \t]*(?:export[ \t]+)?[\"']?"
    rb"("
    rb"[A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL)[A-Z0-9_]*"
    rb"|STOREPASS|KEYPASS|STORE_PASSWORD|KEY_PASSWORD|SIGNING_PASSWORD|STOREPASSWORD|KEYPASSWORD"
    rb")[\"']?"
    rb"[ \t]*[=:][ \t]*(?:\"([^\"\r\n]*)\"|'([^'\r\n]*)'|([^\s#\r\n]+))"
)


class ScanFailure(RuntimeError):
    pass


def release_relative_path(value):
    path = pathlib.PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts:
        return None
    relative = path.as_posix()
    if not relative or any(relative == prefix[:-1] or relative.startswith(prefix) for prefix in EXCLUDED_PREFIXES):
        return None
    return relative


def is_test_path(relative):
    return relative == "tests" or relative.startswith("tests/")


def placeholder(value, *, allow_test_value=False):
    normalized = value.decode("utf-8", "ignore").strip().lower()
    if not normalized:
        return True
    if normalized.startswith(("$", "${", "{{", "<", "example", "dummy", "fake-")):
        return True
    if allow_test_value and normalized.startswith("test-"):
        return True
    if any(marker in normalized for marker in ("your_", "your-", "replace", "placeholder", "changeme", "redacted")):
        return True
    compact = re.sub(r"[^a-z0-9]", "", normalized)
    return len(compact) >= 8 and len(set(compact)) <= 3


def scan_bytes(data, location, *, include_assignments, allow_test_value=False):
    findings = set()
    for category, pattern in HARD_PATTERNS:
        for match in pattern.finditer(data):
            if not placeholder(match.group(0), allow_test_value=allow_test_value):
                findings.add((category, location))
    if include_assignments:
        for match in ASSIGNMENT_PATTERN.finditer(data):
            value = next((part for part in match.groups()[1:] if part is not None), b"")
            if not placeholder(value, allow_test_value=allow_test_value):
                findings.add(("credential assignment", location))
    return findings


def run_git(root, arguments, *, text=False):
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
        text=text,
    )
    if result.returncode:
        raise ScanFailure("Git metadata is unavailable for the required release-history scan")
    return result.stdout


def current_paths(root):
    try:
        raw = run_git(root, ["ls-files", "-co", "--exclude-standard", "-z"])
    except ScanFailure:
        paths = []
        for candidate in root.rglob("*"):
            if candidate.is_file() and not candidate.is_symlink():
                paths.append(candidate.relative_to(root).as_posix())
        return paths
    return [item.decode("utf-8", "surrogateescape") for item in raw.split(b"\0") if item]


def scan_worktree(root):
    findings = set()
    scanned = 0
    for value in current_paths(root):
        relative = release_relative_path(value)
        if relative is None:
            continue
        candidate = root / pathlib.PurePosixPath(relative)
        if not candidate.is_file() or candidate.is_symlink():
            continue
        size = candidate.stat().st_size
        if size > MAX_SOURCE_FILE_BYTES:
            raise ScanFailure(f"Refusing to skip oversized release source: {relative}")
        test_path = is_test_path(relative)
        findings.update(scan_bytes(
            candidate.read_bytes(),
            f"worktree:{relative}",
            include_assignments=not test_path,
            allow_test_value=test_path,
        ))
        scanned += 1
    return findings, scanned


def scan_history(root):
    findings = set()
    scanned = 0
    revisions = [item for item in run_git(root, ["rev-list", "--all"], text=True).splitlines() if item]
    if not revisions:
        raise ScanFailure("Git history is empty; refusing to claim a history scan")
    for revision in revisions:
        listing = run_git(root, ["ls-tree", "-rz", "--full-tree", revision, "--", "."])
        for record in listing.split(b"\0"):
            if not record or b"\t" not in record:
                continue
            metadata, encoded_path = record.split(b"\t", 1)
            fields = metadata.split()
            if len(fields) != 3 or fields[1] != b"blob":
                continue
            raw_relative = encoded_path.decode("utf-8", "surrogateescape")
            if forbidden_signing_path(raw_relative):
                findings.add(("signing material path", f"history:{revision[:12]}:{raw_relative}"))
                continue
            relative = release_relative_path(raw_relative)
            if relative is None:
                continue
            blob = run_git(root, ["cat-file", "blob", fields[2].decode("ascii")])
            if len(blob) > MAX_SOURCE_FILE_BYTES:
                raise ScanFailure(f"Refusing to skip oversized historical release source: {relative}")
            test_path = is_test_path(relative)
            findings.update(scan_bytes(
                blob,
                f"history:{revision[:12]}:{relative}",
                include_assignments=not test_path,
                allow_test_value=test_path,
            ))
            scanned += 1
    return findings, scanned


def scan_apk(path):
    if not path.is_file() or path.is_symlink():
        raise ScanFailure(f"APK is not a regular file: {path}")
    findings = set()
    scanned = 0
    try:
        with zipfile.ZipFile(path) as archive:
            for entry in archive.infolist():
                if entry.is_dir():
                    continue
                findings.update(scan_bytes(
                    archive.read(entry),
                    f"apk:{path.name}:{entry.filename}",
                    include_assignments=False,
                ))
                scanned += 1
    except (OSError, zipfile.BadZipFile) as error:
        raise ScanFailure(f"Unable to inspect APK contents: {path.name}") from error
    return findings, scanned


def forbidden_signing_path(value):
    name = pathlib.PurePosixPath(value.replace("\\", "/")).name.lower()
    return name == "signing.properties" or name.endswith((".keystore", ".jks", ".p12", ".pfx"))


def scan_staged_paths(root):
    findings = set()
    try:
        raw = run_git(root, ["diff", "--cached", "--name-only", "-z"])
    except ScanFailure:
        return findings
    for encoded_path in raw.split(b"\0"):
        if not encoded_path:
            continue
        relative = encoded_path.decode("utf-8", "surrogateescape")
        if forbidden_signing_path(relative):
            findings.add(("staged signing material path", f"index:{relative}"))
    return findings


def main():
    parser = argparse.ArgumentParser(description="Scan Nemotron release sources without printing credential values.")
    parser.add_argument("--root", type=pathlib.Path, default=SCRIPT_ROOT, help="project root to scan")
    parser.add_argument("--current-only", action="store_true", help="skip the required Git-history pass")
    parser.add_argument("--apk", type=pathlib.Path, action="append", default=[], help="signed APK to scan internally")
    arguments = parser.parse_args()
    root = arguments.root.resolve()
    if not root.is_dir():
        raise ScanFailure(f"scan root is not a directory: {root}")

    findings, current_count = scan_worktree(root)
    findings.update(scan_staged_paths(root))
    history_count = 0
    if not arguments.current_only:
        history_findings, history_count = scan_history(root)
        findings.update(history_findings)
    apk_count = 0
    for apk in arguments.apk:
        apk_findings, count = scan_apk(apk.resolve())
        findings.update(apk_findings)
        apk_count += count
    if findings:
        print(f"SECRET_SCAN_FAILED findings={len(findings)}", file=sys.stderr)
        for category, location in sorted(findings):
            print(f"{category}: {location}", file=sys.stderr)
        return 1
    print(f"SECRET_SCAN_OK worktree={current_count} history={history_count} apk_entries={apk_count}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ScanFailure as error:
        print(f"SECRET_SCAN_FAILED {error}", file=sys.stderr)
        raise SystemExit(2)
