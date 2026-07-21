---
name: Android Autonomy Workflows
description: Autonomously open and operate Android apps, search Facebook, create notes, inspect gallery media, browse, download, and install with verified postconditions.
---

# Android autonomy workflows

Use this skill whenever the request involves an Android app, visible UI, gallery/media, Facebook, notes, browsing, downloads, or APK installation. Do the supported work directly; do not ask the user to perform steps that `codex-android`, Shizuku, MediaStore, or the verified acquisition wrappers can perform.

## Universal loop

1. Run `codex-shizuku status` and `codex-android capabilities` when bridge state is unknown.
2. Resolve the app with `codex-android packages '<fragment>'` and open it with `codex-android open '<package-or-fragment>'`.
3. Read the fresh screen with `codex-android dump`; use text/resource descriptions when present and coordinates only from current bounds.
4. Tap/type/swipe, dump again, and verify the requested visible postcondition. Retry bounded alternatives after stale UI or navigation changes.
5. Never bypass Android authentication, device locks, account consent, payment confirmation, or another person's access controls. Report such an actual external gate precisely only after autonomous supported routes are exhausted.

## Facebook and web apps

- Open Facebook, inspect the current UI, use its search field, enter the exact group/page/query, inspect results, and open the exact visible match. Verify the foreground package and target title.
- If the native app lacks a usable route, use a headless web/API route where authenticated and permitted, or open the exact URL visibly and continue UI automation.

## Notes and text entry

- Resolve the installed notes app, open it, inspect UI labels, create the requested note, enter title/body, save using the app's actual control, reopen or search for the title, and verify persisted content.

## Gallery and media

- Use `codex-gallery recent --kind all --hours 24 --limit 100`, `search '<text>'`, or `inspect --kind image|video --id N` before UI automation.
- Open an exact item with `codex-gallery open --kind ... --id N`.
- Delete only explicitly requested exact items with `codex-gallery delete --kind ... --id N --confirm DELETE_MEDIA_ID_N`; the helper moves the exact MediaStore row to Android trash, writes an audit record, verifies normal-gallery absence, and returns its restore confirmation.
- Restore a trashed item with `codex-gallery restore --kind ... --id N --confirm RESTORE_MEDIA_ID_N`; verify that the exact MediaStore row is visible again.
- Find images containing faces locally with `codex-gallery faces --hours N --limit N --min-faces N`. This reports face presence/count only; it does not identify people or infer gender or other sensitive traits.
- Search visible objects, scenes, or text with `codex-gallery semantic '<query>' --hours N --limit N`. Images are resized locally and sent through the current verified zero-price vision route; sensitive-attribute inference is rejected.
- Use installed image/video/OCR tools only after checking the command and preserve originals unless the user explicitly requests mutation.

## Search, download, and install

- Use `codex-search` and `codex-fetch` headlessly, prefer official sources, then `codex-download` with provenance and SHA-256 readback.
- Inspect APK identity/signature before `codex-install`; pin package, signer, and checksum when available, then independently verify the installed base APK, version, signer, and launch state.
- Never treat a browser page, download exit code, or installer launch as completion evidence.
