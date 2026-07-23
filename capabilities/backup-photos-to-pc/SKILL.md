---
name: backup-photos-to-pc
description: Inventory, select, and back up Android gallery photos or videos to the paired PC with source preservation, authenticated routing, checksums, resumable receipts, and destination readback. Use when the user asks to copy, archive, back up, or transfer Android media to their PC.
---

# Back up photos to the paired PC

1. Run `codex-gallery recent` or `search`, then bind the request to exact MediaStore IDs. Do not infer an item from its screen position.
2. Read `metadata` and export a non-destructive original copy into an isolated workspace staging directory. Record source ID, display name, size, MIME type, timestamp, and SHA-256.
3. Run `codex-pc-route select`. Continue only through an authenticated identity-verified file-transfer route. A healthy command gateway without file-transfer support is not sufficient.
4. Inventory the destination before writing. Preserve existing files; on a name collision, compare hashes and either skip an identical file or create an explicit conflict name.
5. Transfer with SSH/SFTP/SCP, signed authenticated SMB, or another configured verified file route. Use bounded retries only when repeating the transfer cannot duplicate or overwrite data.
6. Read back every destination file’s size and SHA-256 from the PC. Record a per-file receipt and a complete manifest.
7. Retain Android originals. Never delete or trash source media as part of backup unless the user separately requests that mutation after the verified backup.
8. Report transferred, identical/skipped, conflicted, and failed counts in English. Do not claim a backup from connectivity, upload exit status, or destination listing alone.

If no authenticated file-transfer route is configured, keep the verified staging manifest and report the exact missing route without opening apps or asking the user to repeat completed inventory work.
