---
name: sync-files-with-pc
description: Safely synchronize explicit Android and paired-PC folders using authenticated identity-verified routes, dry-run manifests, checksums, conflict copies, exclusions, and post-sync readback. Use for one-way or two-way PC/Android file synchronization and cross-device project exchange.
---

# Synchronize files with the paired PC

1. Resolve both roots exactly and refuse broad, protected, credential, runtime-state, or symlink-escaping paths.
2. Select an authenticated route with `codex-pc-route`. Require strict host identity for SSH/SFTP, a pinned HTTPS endpoint, or authenticated signed SMB.
3. Build bounded manifests containing relative path, type, size, modification time, and SHA-256. Exclude secrets, `.git` internals unless explicitly requested, caches, sockets, device files, and live session/WAL state.
4. Produce a dry-run plan: copy to Android, copy to PC, identical, conflict, excluded, and deletion candidates.
5. Default to non-destructive one-way copy. Two-way sync creates conflict copies when both sides changed; it never resolves conflicts by silently selecting the newest timestamp.
6. Enable deletion propagation only when explicitly requested, scoped, recoverable, and proven against the dry-run manifest.
7. Transfer through a resumable tool appropriate to the verified route. Write to a temporary destination and atomically rename after checksum verification when supported.
8. Re-inventory both roots and prove each intended effect. Keep a receipt that supports retry/resume without replaying completed files.

Never share writable Codex runtime, vault, session, memory, or signing state between applications or devices.
