#!/data/data/com.termux/files/usr/bin/python
"""Fail-closed policy shared by Nemotron's Windows PowerShell routes."""

from __future__ import annotations

import json
import ntpath
import re
import shlex
from typing import Iterable, Mapping, Sequence


MAX_COMMAND_CHARS = 16_384
MAX_GATEWAY_PAYLOAD_CHARS = 32_768
MAX_CLEANUP_TARGETS = 16
MAX_CLEANUP_PATH_CHARS = 384
CLEANUP_ACTION = "powershell_cleanup"
CLEANUP_CLASSIFICATIONS = frozenset(
    {"cache", "temp", "redundant-installer", "disposable"}
)
CLEANUP_PHASES = ("inventory", "classify", "exclude", "manifest", "execute", "verify")


class PolicyViolation(ValueError):
    """A request that must be stopped before the Windows gateway is contacted."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _block(code: str) -> None:
    raise PolicyViolation(code)


def sanitized_policy_message(error: PolicyViolation) -> str:
    """Return a stable error that never repeats caller-controlled command/path text."""

    code = error.code if re.fullmatch(r"[a-z0-9_]+", error.code) else "request_blocked"
    return f"PowerShell request blocked by local policy ({code})."


_DYNAMIC_PATTERNS = (
    r"(?<![\w-])(?:invoke-expression|iex)(?![\w-])",
    r"(?:\[\s*)?scriptblock(?:\s*\])?\s*::\s*create\s*\(",
    r"frombase64string\s*\(",
    r"(?<![\w-])(?:-encodedcommand|-enc)(?![\w-])",
    r"(?<![\w-])(?:invoke-command|start-job|start-process|enter-pssession|new-pssession)(?![\w-])",
    r"(?<![\w-])(?:set-alias|new-alias|import-module|add-pssnapin|add-type)(?![\w-])",
    r"(?:system\.diagnostics\.)?process\s*\]?\s*::\s*start\s*\(",
    r"(?:reflection\.assembly|dllimport|invokeverb|\.invoke\s*\()",
    r"(?:(?:::|\.)\s*invoke(?:script|member|method)\s*\(|(?<![\w-])invoke-(?:script|member|method)(?![\w-]))",
    r"(?<![\w-])-(?:membername|methodname)(?![\w-])",
    r"(?<![\w.-])(?:powershell(?:\.exe)?|pwsh(?:\.exe)?)(?![\w.-])",
    r"(?<![\w.-])cmd(?:\.exe)?(?![\w.-])",
    r"(?<![\w.-])(?:wscript|cscript|mshta|rundll32|regsvr32|winrs)(?:\.exe)?(?![\w.-])",
    r"(?<![\w.-])(?:python(?:3|\.\d+)?|node|bash|sh|wsl|perl|ruby)(?:\.exe)?(?![\w.-])",
    r"(?:^|[;|{}()])\s*\.\s+\S",
    r"(?:^|[;|])\s*(?:\.\\|[^\s]+\.ps1(?:\s|$))",
)

_DELETION_PATTERNS = (
    r"(?<![\w-])(?:remove-item(?:property)?|clear-content|clear-item|clear-recyclebin)(?![\w-])",
    r"(?<![\w-])(?:ri|rm|rmdir|del|erase|rd)(?![\w-])",
    r"(?:::|\.)\s*(?:delete|deletefile|deletefolder|deletedirectory)\s*\(",
    r"(?<![\w-])(?:sdelete|shred|unlink|deltree)(?:\.exe)?(?![\w-])",
    r"(?<![\w-])robocopy(?:\.exe)?\b[^\r\n]*(?:/mir|/purge)(?!\w)",
    r"(?<![\w-])(?:fsutil\s+file\s+setzerodata|cipher\s+/w:?)",
    r"(?<![\w-])(?:format-volume|clear-disk|remove-partition)(?![\w-])",
    r"(?<![\w-])git\s+(?:clean\b|reset\s+--hard\b)",
    r"(?:^|[;|])\s*(?:foreach-object|%)\s+(?:delete|deletefile|deletefolder|deletedirectory)(?![\w-])",
    r"(?<![\w-])remove-(?:ciminstance|appxpackage|appxprovisionedpackage|service|computer)(?![\w-])",
    r"(?<![\w-])(?:set-content|add-content|out-file|tee-object|clear-itemproperty)(?![\w-])",
    r"(?<![\w-])(?:move-item|rename-item|copy-item|new-item|set-itemproperty)(?![\w-])",
    r"(?:::|\.)\s*(?:writealltext|writeallbytes|appendalltext|appendalllines|replace|move)\s*\(",
    r"(?<![\w.-])reg(?:\.exe)?\s+(?:add|copy|delete|import|load|restore|save|unload)(?![\w-])",
    r"(?<![\w.-])(?:format(?:\.com|\.exe)?|shutdown(?:\.exe)?|taskkill(?:\.exe)?)(?![\w.-])",
    r"(?<![\w-])(?:stop-computer|restart-computer|stop-process|stop-service|restart-service)(?![\w-])",
)


_READ_ONLY_COMMANDS = frozenset(
    {
        "cat", "compare-object", "convertfrom-csv", "convertfrom-json", "convertfrom-stringdata",
        "convertto-csv", "convertto-html", "convertto-json", "convertto-xml", "dir", "echo",
        "format-custom", "format-hex", "format-list", "format-table", "format-wide", "gc", "gci",
        "gl", "gps", "group-object", "join-path", "ls", "measure-command", "measure-object",
        "out-string", "pwd", "resolve-dnsname", "resolve-path", "select-object", "sort-object",
        "split-path", "tee-object-readonly", "test-connection", "test-netconnection", "test-path",
        "type", "where-object", "write-host", "write-information", "write-output", "write-verbose",
        "write-warning",
    }
)
_READ_ONLY_NATIVE = frozenset(
    {
        "arp", "certutil", "driverquery", "hostname", "ipconfig", "netstat", "nslookup", "pathping",
        "ping", "route", "systeminfo", "tasklist", "tracert", "whoami", "where",
    }
)


def _split_unquoted_pipelines(command: str) -> list[str]:
    segments = []
    start = 0
    quote = None
    for index, character in enumerate(command):
        if quote:
            if character == quote:
                quote = None
            continue
        if character in {"'", '"'}:
            quote = character
        elif character == "|":
            if index + 1 < len(command) and command[index + 1] == "|":
                _block("command_chaining")
            segments.append(command[start:index].strip())
            start = index + 1
    if quote:
        _block("command_quote")
    segments.append(command[start:].strip())
    if not segments or any(not segment for segment in segments):
        _block("command_pipeline")
    return segments


def _command_name(segment: str) -> tuple[str, list[str]]:
    try:
        tokens = shlex.split(segment, posix=False)
    except ValueError:
        _block("command_quote")
    if not tokens:
        _block("command_shape")
    raw = tokens[0].strip('"').casefold().replace("/", "\\")
    name = raw.rsplit("\\", 1)[-1]
    if name.endswith(".exe"):
        name = name[:-4]
    return name, [token.strip('"') for token in tokens[1:]]


def _validate_read_only_segment(segment: str) -> None:
    name, arguments = _command_name(segment)
    if name.startswith(("get-", "test-", "find-", "search-", "show-", "read-")):
        return
    if name in _READ_ONLY_COMMANDS or name in _READ_ONLY_NATIVE:
        return
    if name == "reg" and arguments and arguments[0].casefold() == "query":
        return
    if name == "sc" and arguments and arguments[0].casefold() in {"query", "queryex", "qc", "qdescription"}:
        return
    if name in {"git", "gh"} and arguments == ["--version"]:
        return
    _block("command_not_read_only")


def validate_powershell_command(command: object) -> str:
    """Validate an ordinary, caller-provided PowerShell command."""

    if not isinstance(command, str):
        _block("command_type")
    if not command or command != command.strip() or len(command) > MAX_COMMAND_CHARS:
        _block("command_shape")
    if command == "-" or any(ord(character) < 32 for character in command):
        _block("stdin_or_control")
    lowered = command.casefold()
    if "`" in command or "--%" in command:
        _block("dynamic_syntax")
    if re.search(r"(?<![<>&])&\s*[$('\"{\[]", command):
        _block("dynamic_syntax")
    if re.search(r"(?<![\w-])-(?:file|commandwithargs)(?![\w-])", lowered):
        _block("file_invocation")
    for pattern in _DYNAMIC_PATTERNS:
        if re.search(pattern, lowered):
            _block("dynamic_invocation")
    for pattern in _DELETION_PATTERNS:
        if re.search(pattern, lowered):
            _block("deletion_requires_cleanup")
    if any(character in command for character in ";{}()[]<>") or "#" in command:
        _block("command_structure")
    if re.search(r"(?:^|\s)(?:\$[A-Za-z_][\w:.-]*\s*=|[A-Za-z_][\w.-]*\s*=)", command):
        _block("command_assignment")
    if re.search(r"(^|[^\w])(?:2?>|>>|\*>|&>)", command):
        _block("command_redirection")
    for segment in _split_unquoted_pipelines(command):
        _validate_read_only_segment(segment)
    return command


def validate_github_command(command: object) -> str:
    """Allow one direct git/gh command without PowerShell composition or credential extraction."""

    if not isinstance(command, str) or not command or command != command.strip():
        _block("github_command_shape")
    if len(command) > MAX_COMMAND_CHARS or any(ord(character) < 32 for character in command):
        _block("github_command_shape")
    if any(character in command for character in "`;$|&<>(){}[]#") or "--%" in command:
        _block("github_command_structure")
    try:
        tokens = shlex.split(command, posix=False)
    except ValueError:
        _block("github_command_quote")
    if len(tokens) < 2:
        _block("github_command_shape")
    executable = tokens[0].strip('"').casefold().replace("/", "\\").rsplit("\\", 1)[-1]
    if executable.endswith(".exe"):
        executable = executable[:-4]
    if executable not in {"git", "gh"}:
        _block("github_executable")
    arguments = [token.strip('"').casefold() for token in tokens[1:]]
    if any("credential" in token or "extraheader" in token for token in arguments):
        _block("github_credential_access")
    if executable == "gh" and arguments[:2] == ["auth", "token"]:
        _block("github_credential_access")
    if executable == "git":
        if arguments[0] in {"clean", "restore"}:
            _block("github_destructive_local")
        if arguments[0] == "reset" and any(token in {"--hard", "--merge", "--keep"} for token in arguments[1:]):
            _block("github_destructive_local")
        if arguments[0] in {"checkout", "switch"} and any(token in {"-f", "--force", "--discard-changes"} for token in arguments[1:]):
            _block("github_destructive_local")
    return command


GITHUB_STATUS_COMMAND = (
    "$ErrorActionPreference='Continue';"
    "$git=[bool](Get-Command git -ErrorAction SilentlyContinue);"
    "$gh=[bool](Get-Command gh -ErrorAction SilentlyContinue);"
    "$auth=$false;if($gh){& gh auth status --hostname github.com *> $null;$auth=($LASTEXITCODE -eq 0)};"
    "[pscustomobject]@{ok=$true;gitAvailable=$git;ghAvailable=$gh;authenticated=$auth;verified=$true}"
    "|ConvertTo-Json -Compress"
)


def _canonical_cleanup_path(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_CLEANUP_PATH_CHARS:
        _block("cleanup_path_shape")
    if value != value.strip() or any(ord(character) < 32 for character in value):
        _block("cleanup_path_shape")
    if value.startswith(("\\\\", "//")) or "/" in value:
        _block("cleanup_path_unc")
    if any(character in value for character in "$%*?[]{}'\"`;&|<>"):
        _block("cleanup_path_metacharacter")
    match = re.fullmatch(r"([A-Za-z]):\\(.+)", value)
    if not match:
        _block("cleanup_path_absolute")
    drive, remainder = match.groups()
    raw_parts = remainder.split("\\")
    if any(not part or part in {".", ".."} or part.endswith((" ", ".")) for part in raw_parts):
        _block("cleanup_path_canonical")
    if any(re.search(r"~\d", part, re.IGNORECASE) for part in raw_parts):
        _block("cleanup_path_short_name")
    if any(":" in part for part in raw_parts):
        _block("cleanup_path_stream")
    normalized = ntpath.normpath(f"{drive.upper()}:\\{remainder}")
    if normalized != value:
        _block("cleanup_path_canonical")
    return normalized


_PROTECTED_TOP_LEVEL = {"windows", "program files", "program files (x86)", "programdata"}
_CREDENTIAL_PARTS = {
    ".ssh", ".aws", ".azure", ".gnupg", "ssh", "credential", "credentials",
    "secrets", "keychain", "vault",
}
_CREDENTIAL_FILES = {
    ".git-credentials", ".netrc", "_netrc", "credential.json", "credentials.json",
    "id_rsa", "id_ed25519",
}
_PROJECT_PARTS = {
    ".git", "project", "projects", "repo", "repos", "repositories", "source",
    "src", "workspace", "workspaces", "code", "dev", "development", "git", "github",
}
_CACHE_PARTS = {
    ".cache", "cache", "caches", "code cache", "gpucache", "shadercache",
    "webcache", "inetcache", "npm-cache", "yarn-cache",
}
_TEMP_PARTS = {"temp", "tmp"}
_DISPOSABLE_PARTS = {"disposable", "scratch", "trash", "staging"}
_INSTALLER_SUFFIXES = (".exe", ".msi", ".msix", ".appx", ".appxbundle", ".zip", ".7z", ".iso")


def _cleanup_parts(path: str) -> list[str]:
    return [part.casefold() for part in path[3:].split("\\")]


def _reject_protected_cleanup_path(path: str) -> list[str]:
    parts = _cleanup_parts(path)
    if not parts or parts[0] in _PROTECTED_TOP_LEVEL:
        _block("cleanup_protected_root")
    if any(part in _CREDENTIAL_PARTS for part in parts):
        _block("cleanup_credential_root")
    if parts[-1] in _CREDENTIAL_FILES:
        _block("cleanup_credential_root")
    if any(part in _PROJECT_PARTS for part in parts):
        _block("cleanup_project_root")
    if parts[0] == "users":
        if len(parts) <= 2:
            _block("cleanup_profile_root")
        if parts[2] == "appdata" and len(parts) <= 4:
            _block("cleanup_appdata_root")
    return parts


def _classification_matches(path: str, classification: str, parts: Sequence[str]) -> bool:
    leaf = parts[-1]
    if classification == "cache":
        marker_indexes = [index for index, part in enumerate(parts) if part in _CACHE_PARTS]
        return bool(marker_indexes) and len(parts) >= 4
    if classification == "temp":
        has_bounded_temp_parent = any(
            part in _TEMP_PARTS and index < len(parts) - 1
            for index, part in enumerate(parts)
        )
        return has_bounded_temp_parent or (len(parts) >= 3 and leaf.endswith((".tmp", ".temp")))
    if classification == "redundant-installer":
        return (
            len(parts) >= 2
            and leaf.endswith(_INSTALLER_SUFFIXES)
            and any(token in leaf for token in ("setup", "install", "installer", "update", "upgrade"))
        )
    if classification == "disposable":
        has_bounded_disposable_parent = any(
            part in _DISPOSABLE_PARTS and index < len(parts) - 1
            for index, part in enumerate(parts)
        )
        return has_bounded_disposable_parent or (
            len(parts) >= 3 and leaf.startswith("codex-disposable-")
        )
    return False


def validate_cleanup_request(payload: object) -> dict:
    """Validate and canonicalize the sole structured deletion request."""

    if not isinstance(payload, Mapping) or set(payload) != {"action", "targets"}:
        _block("cleanup_request_schema")
    if payload.get("action") != CLEANUP_ACTION:
        _block("cleanup_action")
    targets = payload.get("targets")
    if not isinstance(targets, list) or not 1 <= len(targets) <= MAX_CLEANUP_TARGETS:
        _block("cleanup_target_count")
    canonical_targets = []
    seen = set()
    for target in targets:
        if not isinstance(target, Mapping) or set(target) != {"path", "classification"}:
            _block("cleanup_target_schema")
        classification = target.get("classification")
        if classification not in CLEANUP_CLASSIFICATIONS:
            _block("cleanup_classification")
        path = _canonical_cleanup_path(target.get("path"))
        folded = path.casefold()
        if folded in seen:
            _block("cleanup_duplicate_target")
        seen.add(folded)
        parts = _reject_protected_cleanup_path(path)
        if not _classification_matches(path, classification, parts):
            _block("cleanup_classification_mismatch")
        canonical_targets.append({"path": path, "classification": classification})
    folded_paths = [target["path"].casefold() for target in canonical_targets]
    for index, first in enumerate(folded_paths):
        for second in folded_paths[index + 1:]:
            if first.startswith(second + "\\") or second.startswith(first + "\\"):
                _block("cleanup_overlapping_targets")
    return {"action": CLEANUP_ACTION, "targets": canonical_targets}


def _powershell_single_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def build_cleanup_script(targets: Iterable[Mapping[str, str]]) -> str:
    """Build the fixed six-phase cleanup program from already validated targets."""

    entries = []
    for target in targets:
        entries.append(
            "    [pscustomobject]@{ LiteralPath = %s; RequestedClassification = %s }"
            % (
                _powershell_single_quote(target["path"]),
                _powershell_single_quote(target["classification"]),
            )
        )
    target_block = ",\n".join(entries)
    template = r'''$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$MaximumTargets = 16
$MaximumChildrenPerTarget = 10000
$RequestedTargets = @(
__TARGETS__
)
$Phases = @()
$Manifest = @()
$Receipts = @()
$ReceiptId = [Guid]::NewGuid().ToString('N')

function Test-ProtectedLiteralPath([string]$LiteralPath) {
    $Path = $LiteralPath.ToLowerInvariant()
    if ($Path -match '^[a-z]:\\$') { return $true }
    if ($Path -match '^[a-z]:\\(?:windows|program files(?: \(x86\))?|programdata)(?:\\|$)') { return $true }
    if ($Path -match '\\(?:\.ssh|\.aws|\.azure|\.gnupg|ssh|credentials?|secrets|keychain|vault)(?:\\|$)') { return $true }
    if ($Path -match '\\(?:\.git-credentials|\.netrc|_netrc|credentials?\.json|id_rsa|id_ed25519)$') { return $true }
    if ($Path -match '\\(?:\.git|projects?|repos?|repositories|source|src|workspaces?|code|dev|development|git|github)(?:\\|$)') { return $true }
    if ($Path -match '^[a-z]:\\users(?:\\[^\\]+)?(?:\\appdata(?:\\(?:local|locallow|roaming))?)?$') { return $true }
    return $false
}

function Test-PathChainSafe([string]$LiteralPath) {
    $FullPath = [IO.Path]::GetFullPath($LiteralPath)
    if ($FullPath -ine $LiteralPath) { return $false }
    $Root = [IO.Path]::GetPathRoot($FullPath)
    if ([string]::IsNullOrWhiteSpace($Root)) { return $false }
    $Current = $Root
    $Relative = $FullPath.Substring($Root.Length)
    foreach ($Part in @($Relative.Split('\') | Where-Object { $_ })) {
        $Current = Join-Path -Path $Current -ChildPath $Part
        $Ancestor = Get-Item -LiteralPath $Current -Force -ErrorAction Stop
        if (($Ancestor.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { return $false }
    }
    return $true
}

function Test-RequestedClassification([string]$LiteralPath, [string]$Classification) {
    $Parts = @($LiteralPath.Substring(3).Split('\') | ForEach-Object { $_.ToLowerInvariant() })
    if ($Parts.Count -eq 0) { return $false }
    $Leaf = $Parts[$Parts.Count - 1]
    if ($Classification -eq 'cache') {
        $Markers = @('.cache', 'cache', 'caches', 'code cache', 'gpucache', 'shadercache', 'webcache', 'inetcache', 'npm-cache', 'yarn-cache')
        return ($Parts.Count -ge 4 -and @($Parts | Where-Object { $Markers -contains $_ }).Count -gt 0)
    }
    if ($Classification -eq 'temp') {
        for ($Index = 0; $Index -lt ($Parts.Count - 1); $Index++) {
            if ($Parts[$Index] -in @('temp', 'tmp')) { return $true }
        }
        return ($Parts.Count -ge 3 -and ($Leaf.EndsWith('.tmp') -or $Leaf.EndsWith('.temp')))
    }
    if ($Classification -eq 'redundant-installer') {
        return ($Parts.Count -ge 2 -and $Leaf -match '(?:setup|install|installer|update|upgrade).*\.(?:exe|msi|msix|appx|appxbundle|zip|7z|iso)$')
    }
    if ($Classification -eq 'disposable') {
        for ($Index = 0; $Index -lt ($Parts.Count - 1); $Index++) {
            if ($Parts[$Index] -in @('disposable', 'scratch', 'trash', 'staging')) { return $true }
        }
        return ($Parts.Count -ge 3 -and $Leaf.StartsWith('codex-disposable-'))
    }
    return $false
}

try {
    if ($RequestedTargets.Count -lt 1 -or $RequestedTargets.Count -gt $MaximumTargets) { throw 'policy' }

    # phase: inventory
    $Phases += 'inventory'
    $Inventory = @($RequestedTargets | ForEach-Object {
        if (-not (Test-PathChainSafe -LiteralPath $_.LiteralPath)) { throw 'policy' }
        $Item = Get-Item -LiteralPath $_.LiteralPath -Force -ErrorAction Stop
        if (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'policy' }
        $Children = @()
        if ($Item.PSIsContainer) {
            $Children = @(Get-ChildItem -LiteralPath $Item.FullName -Force -Recurse -ErrorAction Stop | Select-Object -First ($MaximumChildrenPerTarget + 1))
            if ($Children.Count -gt $MaximumChildrenPerTarget) { throw 'policy' }
            if (@($Children | Where-Object { ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 }).Count -gt 0) { throw 'policy' }
        }
        $Measured = @($Children | Where-Object { -not $_.PSIsContainer } | Measure-Object -Property Length -Sum)
        $Bytes = if ($Item.PSIsContainer) { [long]($Measured.Sum) } else { [long]$Item.Length }
        [pscustomobject]@{
            LiteralPath = $Item.FullName
            RequestedClassification = $_.RequestedClassification
            ItemType = $(if ($Item.PSIsContainer) { 'directory' } else { 'file' })
            ChildCount = $Children.Count
            Bytes = $Bytes
        }
    })

    # phase: classify
    $Phases += 'classify'
    $Classified = @($Inventory | ForEach-Object {
        $ClassificationConfirmed = Test-RequestedClassification -LiteralPath $_.LiteralPath -Classification $_.RequestedClassification
        [pscustomobject]@{
            LiteralPath = $_.LiteralPath
            Classification = $_.RequestedClassification
            ClassificationConfirmed = $ClassificationConfirmed
            ItemType = $_.ItemType
            ChildCount = $_.ChildCount
            Bytes = $_.Bytes
        }
    })

    # phase: exclude
    $Phases += 'exclude'
    $Eligible = @($Classified | Where-Object {
        $_.ClassificationConfirmed -and -not (Test-ProtectedLiteralPath -LiteralPath $_.LiteralPath)
    })
    if ($Eligible.Count -ne $RequestedTargets.Count) { throw 'policy' }

    # phase: manifest
    $Phases += 'manifest'
    $Manifest = @($Eligible | ForEach-Object {
        [pscustomobject]@{
            LiteralPath = $_.LiteralPath
            Classification = $_.Classification
            ItemType = $_.ItemType
            ChildCount = $_.ChildCount
            Bytes = $_.Bytes
        }
    })
    if ($Manifest.Count -lt 1 -or $Manifest.Count -gt $MaximumTargets) { throw 'policy' }
    for ($FirstIndex = 0; $FirstIndex -lt $Manifest.Count; $FirstIndex++) {
        for ($SecondIndex = $FirstIndex + 1; $SecondIndex -lt $Manifest.Count; $SecondIndex++) {
            $FirstPath = $Manifest[$FirstIndex].LiteralPath.TrimEnd('\')
            $SecondPath = $Manifest[$SecondIndex].LiteralPath.TrimEnd('\')
            if ($FirstPath.StartsWith($SecondPath + '\', [StringComparison]::OrdinalIgnoreCase) -or
                $SecondPath.StartsWith($FirstPath + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'policy' }
        }
    }

    # phase: execute
    $Phases += 'execute'
    foreach ($Entry in $Manifest) {
        # Immediate exclusion/classification/readback recheck before execution.
        if (-not (Test-PathChainSafe -LiteralPath $Entry.LiteralPath)) { throw 'policy' }
        $Current = Get-Item -LiteralPath $Entry.LiteralPath -Force -ErrorAction Stop
        if (($Current.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'policy' }
        if ($Current.FullName -ine $Entry.LiteralPath) { throw 'policy' }
        if (Test-ProtectedLiteralPath -LiteralPath $Current.FullName) { throw 'policy' }
        if (-not (Test-RequestedClassification -LiteralPath $Current.FullName -Classification $Entry.Classification)) { throw 'policy' }
        $CurrentChildren = @()
        if ($Current.PSIsContainer) {
            $CurrentChildren = @(Get-ChildItem -LiteralPath $Current.FullName -Force -Recurse -ErrorAction Stop | Select-Object -First ($MaximumChildrenPerTarget + 1))
            if ($CurrentChildren.Count -gt $MaximumChildrenPerTarget) { throw 'policy' }
            if (@($CurrentChildren | Where-Object { ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 }).Count -gt 0) { throw 'policy' }
        }
        Remove-Item -LiteralPath $Current.FullName -Recurse -Force -ErrorAction Stop
        $Removed = -not (Test-Path -LiteralPath $Current.FullName)
        $Receipts += [pscustomobject]@{
            ReceiptId = $ReceiptId
            LiteralPath = $Entry.LiteralPath
            Classification = $Entry.Classification
            Removed = $Removed
            PreviousItemType = $Entry.ItemType
            PreviousChildCount = $Entry.ChildCount
            PreviousBytes = $Entry.Bytes
        }
        if (-not $Removed) { throw 'verification' }
    }

    # phase: verify
    $Phases += 'verify'
    $Verification = @($Manifest | ForEach-Object {
        [pscustomobject]@{
            LiteralPath = $_.LiteralPath
            Classification = $_.Classification
            Removed = -not (Test-Path -LiteralPath $_.LiteralPath)
            PreviousItemType = $_.ItemType
            PreviousChildCount = $_.ChildCount
            PreviousBytes = $_.Bytes
        }
    })
    $Verified = @($Verification | Where-Object { -not $_.Removed }).Count -eq 0
    [pscustomobject]@{
        ok = $Verified
        receiptId = $ReceiptId
        phases = $Phases
        requestedCount = $RequestedTargets.Count
        manifest = $Manifest
        receipts = $Receipts
        verification = $Verification
    } | ConvertTo-Json -Depth 8 -Compress
    if (-not $Verified) { exit 64 }
}
catch {
    [pscustomobject]@{
        ok = $false
        error = 'cleanup_failed'
        receiptId = $ReceiptId
        phases = $Phases
        requestedCount = $RequestedTargets.Count
        manifest = $Manifest
        receipts = $Receipts
        completedCount = $Receipts.Count
    } | ConvertTo-Json -Depth 8 -Compress
    exit 64
}
'''
    return template.replace("__TARGETS__", target_block)


def compatibility_payload(arguments: Sequence[str]) -> dict:
    """Parse the strict powershell/pwsh compatibility command line."""

    args = list(arguments)
    if args and args[0].casefold() == "--cleanup":
        if len(args) != 2 or len(args[1]) > MAX_GATEWAY_PAYLOAD_CHARS:
            _block("cleanup_cli_shape")
        try:
            request = json.loads(args[1])
        except json.JSONDecodeError:
            _block("cleanup_json")
        return validate_cleanup_request(request)
    if len(args) == 2 and args[0].casefold() in {"-command", "-c", "-lc"}:
        command = args[1]
    elif len(args) == 3 and args[0].casefold() == "-l" and args[1].casefold() == "-c":
        command = args[2]
    else:
        _block("cli_invocation")
    return {"action": "powershell", "command": validate_powershell_command(command)}


def parse_gateway_payload(raw_payload: object) -> dict:
    if not isinstance(raw_payload, str) or not raw_payload or len(raw_payload) > MAX_GATEWAY_PAYLOAD_CHARS:
        _block("gateway_payload_shape")
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        _block("gateway_payload_json")
    if not isinstance(payload, dict) or not isinstance(payload.get("action"), str):
        _block("gateway_payload_schema")
    return payload


def validate_powershell_gateway_tail(arguments: Sequence[str]) -> list[str]:
    """Allow only one bounded timeout option after a PowerShell JSON payload."""

    args = list(arguments)
    if not args:
        return args
    if len(args) != 2 or args[0] != "--timeout" or not re.fullmatch(r"[1-9]\d{0,2}", args[1]):
        _block("gateway_cli_ambiguity")
    if int(args[1]) > 300:
        _block("gateway_timeout")
    return args


def prepare_gateway_payload(raw_payload: object) -> str:
    """Validate a codex-win payload and transform structured cleanup locally."""

    payload = parse_gateway_payload(raw_payload)
    action = payload["action"]
    if action.casefold() == "powershell" and action != "powershell":
        _block("powershell_action_case")
    if action == "powershell":
        if set(payload) != {"action", "command"}:
            _block("powershell_payload_schema")
        validated = {
            "action": "powershell",
            "command": validate_powershell_command(payload.get("command")),
        }
        return json.dumps(validated, separators=(",", ":"))
    if action == "powershell_github":
        if set(payload) != {"action", "command"}:
            _block("github_payload_schema")
        validated = {
            "action": "powershell",
            "command": validate_github_command(payload.get("command")),
        }
        return json.dumps(validated, separators=(",", ":"))
    if action == "powershell_github_status":
        if set(payload) != {"action"}:
            _block("github_status_schema")
        return json.dumps(
            {"action": "powershell", "command": GITHUB_STATUS_COMMAND},
            separators=(",", ":"),
        )
    if action.casefold() == CLEANUP_ACTION and action != CLEANUP_ACTION:
        _block("cleanup_action_case")
    if action == CLEANUP_ACTION:
        request = validate_cleanup_request(payload)
        transformed = {
            "action": "powershell",
            "command": build_cleanup_script(request["targets"]),
        }
        return json.dumps(transformed, separators=(",", ":"))
    return raw_payload
