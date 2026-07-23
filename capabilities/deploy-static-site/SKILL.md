---
name: deploy-static-site
description: Build, test, package, and deploy static websites through GitHub Pages, Vercel, Netlify, SSH, or another configured target with source preservation, secret checks, immutable artifact hashes, deployment receipts, and live HTTP verification. Use when the user asks to publish or update a static site.
---

# Deploy a static site

1. Inspect the repository, dirty changes, package scripts, output directory, deployment configuration, and existing remote target. Preserve unrelated work.
2. Verify required credentials through their broker or platform command without printing or copying secrets.
3. Install dependencies only from the project lockfile. Run the project’s formatter/linter, tests, and production build sequentially.
4. Inspect the built output for missing entry points, absolute local paths, source secrets, unsafe symlinks, oversized artifacts, and broken internal references.
5. Hash a deterministic regular-file manifest. Treat this manifest as the deployment input and do not deploy a different working-tree state.
6. Use the configured target adapter: GitHub Pages/Actions, Vercel, Netlify, authenticated SSH/rsync, or another explicit provider. Do not invent Docker or cloud tooling that is unavailable on Android.
7. Capture deployment/project/version identifiers and the final public URL. Poll bounded status until terminal.
8. Fetch the deployed URL headlessly, require the expected status/content identity, and verify representative assets. A push or provider “accepted” response alone is not completion.
9. Record rollback metadata pointing to the prior verified version. Report the build, deployment, and live verification in English.
