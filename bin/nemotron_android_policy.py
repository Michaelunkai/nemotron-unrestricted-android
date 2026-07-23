#!/data/data/com.termux/files/usr/bin/python
"""Shared fail-closed Android/Shizuku policy and verified readback helpers."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import os
import pathlib
import re
import shlex
import stat
import subprocess
import uuid
from typing import Iterable, Sequence


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
RISH = PROJECT_ROOT / "bin" / "rish"
SELF_PACKAGE = "com.michaelovsky.nemotronunrestricted.isolated"
PROTECTED_PACKAGES = frozenset(
    {
        SELF_PACKAGE,
        "com.michaelovsky.codexapplauncher",
        "com.michaelovsky.codexsubscription.isolated",
        "com.michaelovsky.codexnvidia.isolated",
        "com.termux",
        "moe.shizuku.privileged.api",
        "android",
    }
)
PACKAGE_RE = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+$")
PACKAGE_IN_TEXT_RE = re.compile(r"(?<![A-Za-z0-9_])(?:[A-Za-z0-9_]+\.)+[A-Za-z0-9_]+(?![A-Za-z0-9_])")
SHA256_RE = re.compile(r"\b([0-9a-fA-F]{64})\b")
PERMISSION_RE = re.compile(r"\b(?:[A-Za-z0-9_]+\.)+permission\.[A-Za-z0-9_.]+\b")
STAGED_READ_ROOT = pathlib.Path("/storage/emulated/0/Download/.nemotron-tools/readbacks")
DEFAULT_STAGED_READ_MAX_BYTES = 16 * 1024 * 1024

READ_ONLY_PM_ACTIONS = frozenset(
    {
        "dump",
        "get-app-links",
        "get-harmful-app-warning",
        "get-install-location",
        "get-max-users",
        "get-max-running-users",
        "has-feature",
        "list",
        "path",
        "query-activities",
        "query-receivers",
        "query-services",
        "resolve-activity",
    }
)
INSTALL_PM_ACTIONS = frozenset(
    {
        "install",
        "install-abandon",
        "install-commit",
        "install-create",
        "install-existing",
        "install-incremental",
        "install-streaming",
        "install-write",
        "incremental-install",
        "streaming-install",
    }
)
MUTATING_PM_ACTIONS = frozenset(
    {
        *INSTALL_PM_ACTIONS,
        "archive",
        "clear",
        "compile",
        "disable",
        "disable-user",
        "disable-until-used",
        "enable",
        "grant",
        "hide",
        "reconcile-secondary-dex-files",
        "reset-permissions",
        "revoke",
        "set-app-links",
        "set-app-links-allowed",
        "set-app-links-user-selection",
        "set-distracting-restriction",
        "set-harmful-app-warning",
        "set-home-activity",
        "set-install-location",
        "set-installer",
        "suspend",
        "trim-caches",
        "unarchive",
        "unhide",
        "uninstall",
        "unsuspend",
    }
)
READ_ONLY_AM_ACTIONS = frozenset(
    {
        "get-config",
        "get-current-user",
        "get-standby-bucket",
        "monitor",
        "package-importance",
        "start",
        "start-activity",
        "to-app-uri",
        "to-intent-uri",
        "to-uri",
    }
)


class AndroidPolicyError(ValueError):
    """A request that must be stopped before privileged Android execution."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class AndroidBridgeError(RuntimeError):
    """The local rish bridge or remote command did not provide trustworthy state."""

    def __init__(self, code: str, *, remote_status: int | None = None):
        super().__init__(code)
        self.code = code
        self.remote_status = remote_status


@dataclass(frozen=True)
class RemoteResult:
    stdout: str
    stderr: str
    remote_status: int
    outer_status: int

    @property
    def combined(self) -> str:
        if self.stdout and self.stderr:
            return self.stdout.rstrip("\n") + "\n" + self.stderr.lstrip("\n")
        return self.stdout or self.stderr


@dataclass(frozen=True)
class StagedReadback:
    text: str
    sha256: str
    bytes: int
    remote_status: int


def sanitized_policy_message(error: AndroidPolicyError) -> str:
    code = error.code if re.fullmatch(r"[a-z0-9_]+", error.code) else "request_blocked"
    return f"Android request blocked by local policy ({code})."


def validate_package_id(package: object) -> str:
    if package == "android":
        return package
    if not isinstance(package, str) or not PACKAGE_RE.fullmatch(package):
        raise AndroidPolicyError("package_id")
    return package


def is_statically_protected(package: str) -> bool:
    folded = package.casefold()
    return folded in {item.casefold() for item in PROTECTED_PACKAGES} or folded.startswith("com.android.")


def _status_wrapped(command: str, marker: str) -> str:
    return (
        f"{command}\n"
        "__nemotron_remote_status=$?\n"
        f"printf '\\n{marker}%s\\n' \"$__nemotron_remote_status\"\n"
        "exit \"$__nemotron_remote_status\""
    )


def _validated_rish_executable() -> str:
    """Return only a canonical, non-symlinked Nemotron-owned rish launcher."""

    candidate = pathlib.Path(RISH)
    if not candidate.is_absolute():
        raise AndroidBridgeError("bridge_path_untrusted")
    allowed = {
        PROJECT_ROOT / "bin" / "rish",
        PROJECT_ROOT / "runtime" / "home" / ".local" / "bin" / "rish",
    }
    if candidate not in allowed:
        raise AndroidBridgeError("bridge_path_untrusted")
    try:
        root = PROJECT_ROOT.resolve(strict=True)
        current = candidate
        while current != root:
            if current == current.parent or root not in current.parents:
                raise AndroidBridgeError("bridge_path_untrusted")
            if stat.S_ISLNK(current.lstat().st_mode):
                raise AndroidBridgeError("bridge_path_untrusted")
            current = current.parent
        resolved = candidate.resolve(strict=True)
    except (FileNotFoundError, NotADirectoryError, OSError) as error:
        raise AndroidBridgeError("bridge_unavailable") from error
    if resolved != candidate or not stat.S_ISREG(candidate.stat().st_mode):
        raise AndroidBridgeError("bridge_path_untrusted")
    if not os.access(candidate, os.X_OK):
        raise AndroidBridgeError("bridge_unavailable")
    return str(candidate)


def _extract_remote_result(
    stdout: bytes | str,
    stderr: bytes | str,
    outer_status: int,
    marker: str,
) -> RemoteResult:
    if isinstance(stdout, bytes):
        stdout = stdout.decode("utf-8", "replace")
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", "replace")
    pattern = re.compile(re.escape(marker) + r"(-?\d+)")
    matches = pattern.findall(stdout + stderr)
    if len(matches) != 1:
        raise AndroidBridgeError("remote_status_missing")
    remote_status = int(matches[0])
    stdout = pattern.sub("", stdout).strip("\n")
    stderr = pattern.sub("", stderr).strip("\n")
    return RemoteResult(stdout, stderr, remote_status, outer_status)


def run_rish(
    command: str,
    *,
    timeout: float = 45,
    require_success: bool = True,
    input_path: pathlib.Path | None = None,
) -> RemoteResult:
    """Run one rish command and require an unforgeable explicit remote status."""

    marker = "__NEMOTRON_REMOTE_STATUS_%s__:" % uuid.uuid4().hex
    wrapped = _status_wrapped(command, marker)
    rish = _validated_rish_executable()
    try:
        if input_path is None:
            completed = subprocess.run(
                [rish, "-c", wrapped], capture_output=True, timeout=timeout, check=False,
            )
            stdout, stderr, outer_status = completed.stdout, completed.stderr, completed.returncode
        else:
            with open(input_path, "rb") as source:
                process = subprocess.Popen(
                    [rish, "-c", wrapped], stdin=source,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                try:
                    stdout, stderr = process.communicate(timeout=timeout)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()
                    raise AndroidBridgeError("bridge_timeout")
                outer_status = process.returncode
    except (FileNotFoundError, PermissionError) as error:
        raise AndroidBridgeError("bridge_unavailable") from error
    except subprocess.TimeoutExpired as error:
        raise AndroidBridgeError("bridge_timeout") from error
    result = _extract_remote_result(stdout, stderr, outer_status, marker)
    if result.outer_status != 0:
        raise AndroidBridgeError("bridge_process_failed", remote_status=result.remote_status)
    if require_success and result.remote_status != 0:
        raise AndroidBridgeError("remote_command_failed", remote_status=result.remote_status)
    return result


def read_rish_staged(
    command: str,
    *,
    timeout: float = 60,
    max_bytes: int = DEFAULT_STAGED_READ_MAX_BYTES,
) -> StagedReadback:
    """Read large remote text without trusting rish stdout/stderr stream placement."""

    if (
        not isinstance(command, str)
        or not command.strip()
        or "\x00" in command
        or isinstance(max_bytes, bool)
        or not isinstance(max_bytes, int)
        or not 1 <= max_bytes <= 128 * 1024 * 1024
    ):
        raise AndroidPolicyError("staged_readback_request")
    STAGED_READ_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    local = STAGED_READ_ROOT / f"readback-{uuid.uuid4().hex}.txt"
    quoted = shlex.quote(str(local))
    staged_command = (
        f"( {command} ) > {quoted} 2>&1; "
        "__nemotron_readback_status=$?; "
        "if [ \"$__nemotron_readback_status\" -ne 0 ]; then "
        f"rm -f {quoted}; exit \"$__nemotron_readback_status\"; fi; "
        f"__nemotron_readback_bytes=$(wc -c < {quoted}) || exit $?; "
        f"__nemotron_readback_sha=$(sha256sum {quoted} | cut -d' ' -f1) || exit $?; "
        "printf 'NEMOTRON_READBACK bytes=%s sha256=%s\\n' "
        "\"$__nemotron_readback_bytes\" \"$__nemotron_readback_sha\""
    )
    receipt = run_rish(staged_command, timeout=timeout, require_success=False)
    try:
        if receipt.remote_status != 0:
            raise AndroidBridgeError(
                "staged_readback_remote_failed", remote_status=receipt.remote_status,
            )
        match = re.search(
            r"NEMOTRON_READBACK bytes=(\d+) sha256=([0-9a-fA-F]{64})\b",
            receipt.combined,
        )
        if match is None:
            raise AndroidBridgeError("staged_readback_receipt_invalid")
        expected_bytes = int(match.group(1))
        expected_sha = match.group(2).casefold()
        if not 0 <= expected_bytes <= max_bytes:
            raise AndroidBridgeError("staged_readback_size_invalid")
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(local, flags)
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_size != expected_bytes
                or metadata.st_size > max_bytes
            ):
                raise AndroidBridgeError("staged_readback_file_invalid")
            chunks = []
            remaining = expected_bytes
            while remaining:
                chunk = os.read(descriptor, min(remaining, 1024 * 1024))
                if not chunk:
                    raise AndroidBridgeError("staged_readback_truncated")
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(descriptor, 1):
                raise AndroidBridgeError("staged_readback_size_changed")
        finally:
            os.close(descriptor)
        data = b"".join(chunks)
        observed_sha = hashlib.sha256(data).hexdigest()
        if observed_sha != expected_sha:
            raise AndroidBridgeError("staged_readback_integrity_failed")
        try:
            text = data.decode("utf-8", "strict")
        except UnicodeDecodeError as error:
            raise AndroidBridgeError("staged_readback_utf8_invalid") from error
        return StagedReadback(text, observed_sha, expected_bytes, receipt.remote_status)
    except OSError as error:
        raise AndroidBridgeError("staged_readback_file_unavailable") from error
    finally:
        local.unlink(missing_ok=True)


def verify_png_file(path: pathlib.Path, *, max_bytes: int = 64 * 1024 * 1024) -> dict:
    """Decode and hash one non-symlinked PNG instead of trusting command success."""

    path = pathlib.Path(path)
    if (
        not path.is_absolute()
        or isinstance(max_bytes, bool)
        or not isinstance(max_bytes, int)
        or not 8 <= max_bytes <= 256 * 1024 * 1024
    ):
        raise AndroidPolicyError("png_verification_request")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or not 8 <= metadata.st_size <= max_bytes
            ):
                raise AndroidBridgeError("png_file_invalid")
            chunks = []
            remaining = metadata.st_size
            while remaining:
                chunk = os.read(descriptor, min(remaining, 1024 * 1024))
                if not chunk:
                    raise AndroidBridgeError("png_file_truncated")
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(descriptor, 1):
                raise AndroidBridgeError("png_file_size_changed")
        finally:
            os.close(descriptor)
    except OSError as error:
        raise AndroidBridgeError("png_file_unavailable") from error
    data = b"".join(chunks)
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise AndroidBridgeError("png_signature_invalid")
    try:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            image_format = image.format
            width, height = image.size
    except (ImportError, OSError, ValueError) as error:
        raise AndroidBridgeError("png_decode_invalid") from error
    if image_format != "PNG" or not 1 <= width <= 32768 or not 1 <= height <= 32768:
        raise AndroidBridgeError("png_dimensions_invalid")
    return {
        "path": str(path),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "format": "PNG",
        "width": width,
        "height": height,
        "verified": True,
    }


def parse_package_lines(text: str) -> list[str]:
    packages = []
    for line in text.splitlines():
        if line.startswith("package:"):
            package = line.partition(":")[2].strip()
            if package == "android" or PACKAGE_RE.fullmatch(package):
                packages.append(package)
    return sorted(set(packages))


def list_packages(fragment: str | None = None) -> list[str]:
    result = run_rish("pm list packages --user 0")
    packages = parse_package_lines(result.combined)
    if not packages:
        raise AndroidBridgeError("package_list_empty")
    if fragment:
        folded = fragment.casefold()
        packages = [package for package in packages if folded in package.casefold()]
    return packages


def package_paths(package: str, *, known_installed: bool | None = None) -> list[str]:
    package = validate_package_id(package)
    if known_installed is None:
        known_installed = package in list_packages(package)
    if not known_installed:
        return []
    result = run_rish(f"pm path --user 0 {shlex.quote(package)}")
    paths = [line.partition(":")[2].strip() for line in result.combined.splitlines()
             if line.startswith("package:") and line.partition(":")[2].strip().startswith("/")]
    if not paths:
        raise AndroidBridgeError("package_path_missing")
    return paths


def package_dump(package: str) -> str:
    package = validate_package_id(package)
    return run_rish(f"dumpsys package {shlex.quote(package)}").combined


def package_is_system(package: str, dump: str | None = None) -> bool:
    package = validate_package_id(package)
    if is_statically_protected(package):
        return True
    if dump is None:
        if package not in list_packages(package):
            return False
        dump = package_dump(package)
    return bool(re.search(r"(?:pkgFlags|flags)=\[[^]]*\bSYSTEM\b", dump, re.IGNORECASE)
                or re.search(r"(?:^|\s)(?:codePath|path)=/(?:system|product|vendor|system_ext|odm)/", dump))


def apk_signer(path: str) -> tuple[str | None, bool]:
    if not path or not os.access(path, os.R_OK):
        return None, False
    try:
        completed = subprocess.run(
            ["apksigner", "verify", "--verbose", "--print-certs", path],
            capture_output=True, text=True, timeout=45, check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None, False
    text = completed.stdout + completed.stderr
    match = re.search(r"certificate SHA-256 digest:\s*([0-9a-fA-F]{64})", text, re.IGNORECASE)
    return (match.group(1).lower() if match else None), completed.returncode == 0 and bool(match)


def package_evidence(package: str) -> dict:
    package = validate_package_id(package)
    installed = package in list_packages(package)
    if not installed:
        return {"ok": True, "installed": False, "package": package,
                "protected": is_statically_protected(package), "verified": True}
    paths = package_paths(package, known_installed=True)
    base_path = paths[0]
    dump = package_dump(package)
    hash_result = run_rish(f"sha256sum {shlex.quote(base_path)}")
    hash_match = SHA256_RE.search(hash_result.combined)
    apk_hash = hash_match.group(1).lower() if hash_match else None
    second_paths = package_paths(package, known_installed=True)
    version_match = re.search(r"^\s*versionName=(.*)$", dump, re.MULTILINE)
    code_match = re.search(r"^\s*versionCode=(\d+)", dump, re.MULTILINE)
    signer, signature_verified = apk_signer(base_path)
    permissions = sorted(set(PERMISSION_RE.findall(dump)))
    system = package_is_system(package, dump)
    path_stable = paths == second_paths
    verified = bool(path_stable and apk_hash and signer and signature_verified)
    return {"ok": True, "installed": True, "package": package, "path": base_path,
            "splitPaths": paths[1:], "version": version_match.group(1).strip() if version_match else None,
            "versionCode": int(code_match.group(1)) if code_match else None, "sha256": apk_hash,
            "signerSha256": signer, "signatureVerified": signature_verified,
            "permissions": permissions, "system": system,
            "protected": is_statically_protected(package) or system,
            "pathStable": path_stable, "verified": verified}


def candidate_packages(values: Iterable[str]) -> list[str]:
    """Extract plausible package identifiers from a list of arguments."""

    candidates = []
    for value in values:
        for match in PACKAGE_IN_TEXT_RE.findall(str(value)):
            if match not in candidates:
                candidates.append(match)
        if value == "android" and value not in candidates:
            candidates.append(value)
    return candidates


def package_is_protected(package: str) -> bool:
    package = validate_package_id(package)
    if is_statically_protected(package):
        return True
    try:
        return package_is_system(package)
    except AndroidBridgeError:
        # A mutation must not proceed when system/protected classification is unavailable.
        raise AndroidPolicyError("package_classification_unavailable")


def _shell_tokens(command: str) -> list[str]:
    if not isinstance(command, str) or not command.strip() or "\x00" in command:
        raise AndroidPolicyError("shell_command_shape")
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()")
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        return list(lexer)
    except ValueError as error:
        raise AndroidPolicyError("shell_command_parse") from error


_SHELL_INDIRECTION_COMMANDS = frozenset({
    "alias", "ash", "awk", "bash", "busybox", "command", "dash", "env", "eval",
    "exec", "find", "ksh", "mksh", "node", "perl", "python", "python3", "ruby",
    "sh", "toybox", "xargs", "zsh",
})
_READ_ONLY_ANDROID_SHELL_COMMANDS = frozenset({
    "df", "dumpsys", "du", "getconf", "getprop", "id", "ip", "netstat",
    "pidof", "printenv", "ps", "sha256sum", "ss", "stat", "uname", "uptime",
    "whoami", "wm",
})


def _simple_direct_shell_tokens(command: str) -> list[str]:
    """Accept one direct argv-like command and reject shell-computed execution."""

    if any(character in command for character in "\x00\r\n\t;&|()<>$`"):
        raise AndroidPolicyError("shell_indirection")
    tokens = _shell_tokens(command)
    if not tokens:
        raise AndroidPolicyError("shell_command_shape")
    executable = tokens[0].casefold().rsplit("/", 1)[-1]
    if executable in _SHELL_INDIRECTION_COMMANDS or "=" in tokens[0]:
        raise AndroidPolicyError("shell_indirection")
    return tokens


def _direct_android_route(tokens: Sequence[str]) -> tuple[str, str] | None:
    lowered = [token.casefold() for token in tokens]
    executable = lowered[0].rsplit("/", 1)[-1]
    if executable == "pm":
        return "pm", lowered[1] if len(lowered) > 1 else ""
    if executable == "cmd" and len(lowered) > 1 and lowered[1] == "package":
        return "pm", lowered[2] if len(lowered) > 2 else ""
    if executable == "am":
        return "am", lowered[1] if len(lowered) > 1 else ""
    if executable in {"appops", "service"}:
        return executable, lowered[1] if len(lowered) > 1 else ""
    return None


def validate_android_shell_command(command: object) -> str:
    if not isinstance(command, str) or len(command) > 32768:
        raise AndroidPolicyError("shell_command_shape")
    tokens = _simple_direct_shell_tokens(command)
    route = _direct_android_route(tokens)
    if route is None:
        executable = tokens[0].casefold().rsplit("/", 1)[-1]
        if executable == "settings":
            if len(tokens) < 2 or tokens[1].casefold() not in {"get", "list"}:
                raise AndroidPolicyError("settings_mutation_requires_structured_route")
            return command
        if executable not in _READ_ONLY_ANDROID_SHELL_COMMANDS:
            raise AndroidPolicyError("shell_command_not_read_only")
        return command
    namespace, action = route
    if namespace == "pm" and action not in READ_ONLY_PM_ACTIONS:
        raise AndroidPolicyError("package_mutation_requires_structured_route")
    if namespace == "am" and action not in READ_ONLY_AM_ACTIONS:
        raise AndroidPolicyError("package_mutation_requires_structured_route")
    if namespace == "appops" and action not in {"get", "query-op", "query-op-user"}:
        raise AndroidPolicyError("package_mutation_requires_structured_route")
    if namespace == "service":
        raise AndroidPolicyError("package_mutation_requires_structured_route")
    return command


def validate_pm_arguments(arguments: Sequence[str]) -> list[str]:
    args = list(arguments)
    if not args:
        raise AndroidPolicyError("pm_arguments")
    action = args[0].casefold()
    if action in INSTALL_PM_ACTIONS or action.startswith("install-"):
        raise AndroidPolicyError("install_requires_codex_install")
    if action == "uninstall":
        raise AndroidPolicyError("uninstall_requires_codex_uninstall")
    mutating = action in MUTATING_PM_ACTIONS or action not in READ_ONLY_PM_ACTIONS
    if not mutating:
        return args
    packages = candidate_packages(args[1:])
    if not packages and action not in {"reset-permissions", "trim-caches", "set-install-location"}:
        raise AndroidPolicyError("mutation_target_missing")
    if any(package_is_protected(package) for package in packages):
        raise AndroidPolicyError("protected_package_mutation")
    return args


def validate_sha256(value: object, *, required: bool = False) -> str | None:
    if value in {None, ""}:
        if required:
            raise AndroidPolicyError("sha256_required")
        return None
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise AndroidPolicyError("sha256_shape")
    return value.lower()
