# OAP-app Web Deploy Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Automate OAP-app web static export and deployment to `oa-reader.unself.cn` via Gitea Actions.

**Architecture:** Single Gitea Actions workflow on `ubuntu-local` runner. Metro bundler produces static files in `dist/`, deployed via `sshpass + ssh/scp` to OpenResty.

**Tech Stack:** Expo SDK 54, Metro bundler, npm, Gitea Actions, sshpass

**Design doc:** `docs/plans/2026-04-12-web-deploy-design.md`

---

### Task 1: Add `build:web` script to package.json

**Files:**
- Modify: `OAP-app/package.json:5-12` (scripts section)

**Step 1: Add the script**

In `OAP-app/package.json`, add `"build:web"` to the `scripts` object:

```json
"scripts": {
  "start": "expo start",
  "reset-project": "node ./scripts/reset-project.js",
  "android": "expo start --android",
  "ios": "expo start --ios",
  "web": "expo start --web",
  "build:web": "npx expo export --platform web",
  "lint": "expo lint"
}
```

**Step 2: Verify script is registered**

Run: `cd OAP-app && npm run build:web -- --help 2>&1 | head -5`
Expected: Output shows expo export usage/help (does not actually build since `--help` short-circuits)



---

### Task 2: Update .gitignore for dist/

**Files:**
- Modify: `OAP-app/.gitignore`

**Step 1: Add dist/ to gitignore**

Append to `OAP-app/.gitignore`:

```
dist/
```

**Step 2: Remove tracked dist/ from Git index**

Run: `git rm -r --cached OAP-app/dist`
Expected: Shows all dist/ files being removed from index (files stay on disk)

**Step 3: Verify dist/ is ignored**

Run: `git status OAP-app/dist`
Expected: "nothing to commit" or no output (ignored)

**Step 4: Commit**

```bash
git add OAP-app/.gitignore
git commit -m "chore(oap-app): add dist/ to gitignore and untrack"
```

---

### Task 3: Create workflow file

**Files:**
- Create: `.github/workflows/web-deploy.yml`

**Step 1: Create the workflow**

Create `.github/workflows/web-deploy.yml` with:

```yaml
name: Web Deploy (OAP-app)

on:
  workflow_dispatch:
  push:
    branches:
      - main
    paths:
      - "OAP-app/**"
      - ".github/workflows/web-deploy.yml"

permissions:
  contents: read

concurrency:
  group: web-deploy
  cancel-in-progress: true

env:
  APP_PATH: OAP-app

jobs:
  deploy:
    runs-on: ubuntu-local
    timeout-minutes: 10
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: "20"

      - name: Cache node_modules
        uses: actions/cache@v4
        with:
          path: ${{ env.APP_PATH }}/node_modules
          key: npm-web-${{ hashFiles('OAP-app/package-lock.json') }}
          restore-keys: npm-web-

      - name: Install dependencies
        working-directory: ${{ env.APP_PATH }}
        run: npm ci

      - name: Build web
        working-directory: ${{ env.APP_PATH }}
        run: npm run build:web

      - name: Deploy to server
        env:
          DEPLOY_HOST: ${{ secrets.DEPLOY_HOST }}
          DEPLOY_USER: ${{ secrets.DEPLOY_USER }}
          DEPLOY_PASS: ${{ secrets.DEPLOY_PASS }}
          DEPLOY_PATH: ${{ secrets.DEPLOY_PATH }}
        run: |
          set -euo pipefail
          sshpass -p "$DEPLOY_PASS" ssh -o StrictHostKeyChecking=no \
            "${DEPLOY_USER}@${DEPLOY_HOST}" \
            "rm -rf ${DEPLOY_PATH}/*"
          sshpass -p "$DEPLOY_PASS" scp -o StrictHostKeyChecking=no \
            -r ${{ env.APP_PATH }}/dist/* \
            "${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}/"
          sshpass -p "$DEPLOY_PASS" ssh -o StrictHostKeyChecking=no \
            "${DEPLOY_USER}@${DEPLOY_HOST}" \
            "chown -R 1000:1000 ${DEPLOY_PATH}"

      - name: Deploy summary
        run: |
          echo "## Web Deploy Complete" >> "$GITHUB_STEP_SUMMARY"
          echo "- Branch: \`${{ github.ref_name }}\`" >> "$GITHUB_STEP_SUMMARY"
          echo "- Commit: \`${{ github.sha }}\`" >> "$GITHUB_STEP_SUMMARY"
```

**Step 2: Validate YAML syntax**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/web-deploy.yml'))"`
Expected: No error (empty output = valid YAML)


---

### Task 4: Configure Gitea Secrets (manual)

**No files changed.**

This is a manual step the user must perform in Gitea UI:

1. Go to Gitea → Repository → Settings → Secrets
2. Add 4 secrets:

| Secret | Value |
|--------|-------|
| `DEPLOY_HOST` | Server hostname/IP |
| `DEPLOY_USER` | SSH username |
| `DEPLOY_PASS` | SSH password |
| `DEPLOY_PATH` | `/opt/1panel/www/sites/oa-reader.unself.cn/index` |

3. Verify `sshpass` is installed on the `ubuntu-local` runner:
   ```bash
   which sshpass || sudo apt install -y sshpass
   ```

---

### Task 5: Manual trigger test

**No files changed.**

**Step 1: Push all commits**

Run: `git push origin main`

**Step 2: Trigger workflow manually**

Go to Gitea → Repository → Actions → Web Deploy (OAP-app) → Run workflow

**Step 3: Verify**

- Build step should produce `OAP-app/dist/` with `index.html` and bundled assets
- Deploy step should upload files to server
- Visit `https://oa-reader.unself.cn` to verify the app loads
