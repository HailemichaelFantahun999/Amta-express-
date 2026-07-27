# Amta Express — Full Setup & Release Workflow Guide

This walks through everything from an empty local folder to shipping a
tagged, versioned release to production. Follow it in order the first time;
after that, jump to whichever section you need.

---

## Part 1 — One-time repository setup

### 1.1 Create the GitHub repo

Already covered in detail earlier — quick recap:

1. https://github.com/new
2. Name: `amta-express`, Visibility: **Private**
3. Leave README/.gitignore/license **unchecked**
4. Create repository, copy the remote URL shown

### 1.2 Enable GHCR write permission

Required or every build/tag workflow will fail at the push step.

1. Repo → **Settings → Actions → General**
2. Scroll to **Workflow permissions**
3. Select **Read and write permissions**
4. **Save**

### 1.3 Add the deployment secrets

Repo → **Settings → Secrets and variables → Actions → Repository secrets → New repository secret**. Add all six:

```
STAGING_HOST       e.g. 137.184.199.221
STAGING_USER       e.g. amta
STAGING_SSH_KEY    private key matching a public key on the staging server

PROD_HOST          e.g. 198.211.104.207
PROD_USER          e.g. amta
PROD_SSH_KEY       private key matching a public key on the production server
```

(These servers don't need to exist yet to do Part 2 — you'll hit an SSH
connection error at deploy time until they're provisioned, which is
expected and fine for now.)

---

## Part 2 — Initialize and push the scaffold

From inside the unzipped `amta-express/` folder:

```bash
git init
git branch -M main
git add .
git commit -m "chore: initial project scaffold"
git remote add origin git@github.com:<your-username>/amta-express.git
git push -u origin main
```

Create the other two long-lived branches from `main`:

```bash
git checkout -b develop
git push -u origin develop

git checkout -b staging
git push -u origin staging

git checkout main
```

**Verify:** GitHub → your repo → branch dropdown should show `main`, `develop`, `staging`, all identical right now.

---

## Part 3 — Normal feature development

### 3.1 Start a feature

```bash
git checkout develop
git pull origin develop
git checkout -b feature/order-tracking
```

### 3.2 Work, commit, push

```bash
git add .
git commit -m "feat(orders): add tracking endpoint"
git push -u origin feature/order-tracking
```

### 3.3 Open a PR into `develop`

```bash
gh pr create --base develop --head feature/order-tracking \
  --title "feat(orders): add tracking endpoint" \
  --body "Adds GET /api/v1/orders/{id}/tracking"
```

Or via the GitHub UI. `ci.yml` runs automatically on this PR (lint, test, build, docker validate).

### 3.4 Merge, then delete the branch

```bash
gh pr merge --squash --delete-branch
```

---

## Part 4 — Promote develop → staging (manual, by design)

```bash
git checkout staging
git pull origin staging
git merge develop --no-edit
git push origin staging
```

**What happens automatically:** `deploy-staging.yml` fires on this push — builds images, pushes to GHCR, SSHs into the staging server, deploys, runs migrations, health-checks `https://staging.amtaexpress.com/health/`.

Go watch it: repo → **Actions** tab → the running workflow.

---

## Part 5 — Promote staging → main (manual PR)

Once staging is validated:

```bash
gh pr create --base main --head staging \
  --title "Release: promote staging to main" \
  --body "Staging validated. Ready for release."
```

Review the diff, then merge (squash merge, per your branch strategy):

```bash
gh pr merge --squash
```

**What happens automatically:** `build-production.yml` fires on this merge — builds backend/frontend images, tags them `sha-<commit>` and `production`, pushes to GHCR. **Nothing deploys yet.** Check the run's summary (Actions tab → the run → Summary) for the exact `sha-` version and the suggested `git tag` command.

---

## Part 6 — Create the official release tag

This is the step that makes it a real, numbered release instead of just a build.

### 6.1 Decide the version number

```
MAJOR.MINOR.PATCH
```

- New backward-compatible feature (like the order tracking example above) → bump **MINOR**: `v1.3.0` → `v1.4.0`
- Bug fix only → bump **PATCH**: `v1.4.0` → `v1.4.1`
- Breaking API/database change → bump **MAJOR**: `v1.4.0` → `v2.0.0`

Check your last tag if unsure:

```bash
git fetch --tags
git tag --sort=-v:refname | head -5
```

### 6.2 Create and push the tag

```bash
git checkout main
git pull origin main
git tag v1.4.0
git push origin v1.4.0
```

**What happens automatically:** `tag-release.yml` fires —

1. Verifies the `sha-<commit>` image from Part 5 actually exists in GHCR
2. Re-labels that exact image with `v1.4.0` (no rebuild — confirmed same digest)
3. Creates a GitHub Release at **repo → Releases** with auto-generated notes (list of merged PRs since the last tag)

Check it: **repo → Releases** — you should see `v1.4.0` listed with a changelog.

---

## Part 7 — Deploy the release to production

This is the manual approval gate — nothing reaches production without this explicit action.

1. Go to **repo → Actions → Deploy to Production** (left sidebar)
2. Click **Run workflow** (top right)
3. In the **version** field, type: `v1.4.0`
4. Click the green **Run workflow** button

Watch the run. It will:
- SSH into the production server
- Pull the `v1.4.0` images
- Run database migrations
- Restart containers
- Health-check `https://www.amtaexpress.com/health/`

If the health check fails, the run shows red — do not consider it deployed, investigate immediately.

---

## Part 8 — Emergency fix (see the dedicated runbook)

If production breaks and can't wait for the full flow above, use:

```
docs/runbooks/hotfix.md
```

Quick summary of that path:

```bash
git checkout main && git pull origin main
git checkout -b hotfix/payment-timeout
# fix, commit, push
gh pr create --base main --head hotfix/payment-timeout --title "hotfix: ..."
gh pr merge --squash
git tag v1.4.1 && git push origin v1.4.1
# Actions → Deploy to Production → Run workflow → v1.4.1
# then backport: merge main into staging AND develop
```

---

## Quick reference — full command sequence, start to finish

```bash
# One-time
git init
git branch -M main
git add .
git commit -m "chore: initial project scaffold"
git remote add origin git@github.com:<you>/amta-express.git
git push -u origin main
git checkout -b develop && git push -u origin develop
git checkout -b staging && git push -u origin staging
git checkout main

# Per feature
git checkout develop && git pull origin develop
git checkout -b feature/<name>
# ...work...
git push -u origin feature/<name>
gh pr create --base develop --head feature/<name>
gh pr merge --squash --delete-branch

# Promote to staging (manual, triggers auto-deploy to staging)
git checkout staging && git pull origin staging
git merge develop --no-edit
git push origin staging

# Promote to production (manual PR)
gh pr create --base main --head staging
gh pr merge --squash

# Tag the release (triggers re-label + GitHub Release, no rebuild)
git checkout main && git pull origin main
git tag vX.Y.Z
git push origin vX.Y.Z

# Deploy (manual, via GitHub UI)
# Actions → Deploy to Production → Run workflow → enter vX.Y.Z
```