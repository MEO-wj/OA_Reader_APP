# OAP-app Web Deploy CI/CD Design

## Goal

Automate OAP-app web build and deployment to `oa-reader.unself.cn` via Gitea Actions.

## Context

- OAP-app uses Expo SDK 54 + Metro bundler, already configured for static web export (`app.json`: `"web": { "output": "static" }`)
- Existing `dist/` directory committed to Git — needs cleanup
- Target server: OpenResty (Nginx) on self-hosted machine, path: `/opt/1panel/www/sites/oa-reader.unself.cn/index`
- CI runner: `ubuntu-local` (self-hosted Gitea Actions runner)
- Package manager: npm + `package-lock.json`

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `.github/workflows/web-deploy.yml` | Create | Build + deploy workflow |
| `OAP-app/package.json` | Modify | Add `build:web` script |
| `OAP-app/.gitignore` | Modify | Add `dist/` pattern |

## Workflow Design

### Trigger

- `workflow_dispatch` (manual)
- Push to `main` when `OAP-app/**` or `.github/workflows/web-deploy.yml` changes

### Concurrency

- Group: `web-deploy`
- `cancel-in-progress: true` — only keep the latest deployment

### Steps

1. Checkout code
2. Setup Node.js 20
3. Cache `OAP-app/node_modules` (key: `npm-web-<hash of package-lock.json>`)
4. `npm ci` (in OAP-app directory)
5. `npm run build:web` (runs `npx expo export --platform web`)
6. Clean remote directory via `sshpass + ssh`
7. Upload `dist/*` via `sshpass + scp`
8. Set file ownership via `sshpass + ssh`

### Secrets Required

| Secret | Description |
|--------|-------------|
| `DEPLOY_HOST` | Server hostname/IP |
| `DEPLOY_USER` | SSH username |
| `DEPLOY_PASS` | SSH password |
| `DEPLOY_PATH` | `/opt/1panel/www/sites/oa-reader.unself.cn/index` |

### Error Handling

- `set -euo pipefail` on all shell steps
- Clean-then-upload strategy prevents stale file accumulation
- Build failure naturally prevents deployment (step ordering)
- No rollback mechanism (re-run workflow to redeploy)

## Notes

- **SPA fallback**: Expo export generates individual HTML files for static routes (e.g., `explore.html`, `login.html`). If dynamic routes are added later (e.g., `/article/123`), OpenResty will need `try_files $uri $uri/ /index.html` configuration to avoid 404s.
- **`_redirects` and `vercel.json`**: These are for Netlify/Vercel respectively and have no effect on OpenResty. They can be ignored.
