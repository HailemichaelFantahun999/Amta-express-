# Runbook: Hotfix (Critical Production Issue)

**Use this when:** production is broken or badly degraded right now, and the
fix cannot wait for the normal `feature → develop → staging → main` flow.

**Do not use this for:** routine bugs, anything that can go through the
normal pipeline without meaningful customer impact. Hotfixes skip staging
soak time — only use this path when that trade-off is justified.

---

## 1. Create the hotfix branch from `main`

`main` is production. Branch from it directly so the fix contains nothing
except what's already live plus your change.

```bash
git checkout main
git pull origin main
git checkout -b hotfix/<short-description>
```

Example: `hotfix/payment-timeout`, `hotfix/login-500-error`

---

## 2. Make the smallest fix that resolves the issue

- Keep the diff minimal. This is not the time for refactors or unrelated cleanup.
- Add or update a test that covers the failure, if at all possible — even a
  quick regression test is worth it.

```bash
git add .
git commit -m "fix(payments): resolve timeout on retry (hotfix)"
git push -u origin hotfix/payment-timeout
```

Pushing immediately runs CI (`ci.yml` triggers on any `hotfix/**` push), so
you get lint/test feedback before you even open the PR.

---

## 3. Open a PR directly into `main`

```bash
gh pr create --base main --head hotfix/payment-timeout \
  --title "hotfix: resolve payment timeout on retry" \
  --body "Critical fix — see incident #<id if applicable>. Skips staging due to production impact."
```

Or open it from the GitHub web UI: **Pull requests → New pull request**,
base = `main`, compare = `hotfix/payment-timeout`.

Get an expedited review — even a quick second pair of eyes — before merging.
Branch protection isn't enforced on this plan, so nothing stops a direct
merge, but skipping review on a production fix is exactly how hotfixes cause
a second incident.

---

## 4. Merge the PR

Squash and merge, same as any other PR. This triggers `build-production.yml`
automatically (it runs on every push to `main`), which builds and pushes new
`amta-backend`/`amta-frontend` images tagged with the new commit SHA.

---

## 5. Tag the release (PATCH version)

Hotfixes are PATCH releases (per Release Management standard — bug fixes,
security patches). Once the build above has finished successfully:

```bash
git checkout main
git pull origin main
git tag v1.4.3   # increment PATCH from the last release
git push origin v1.4.3
```

This triggers `tag-release.yml`, which re-labels the already-built image
with the version number (no rebuild) and creates a GitHub Release.

---

## 6. Deploy manually

Go to **Actions → Deploy to Production → Run workflow**, enter the version
you just tagged (e.g. `v1.4.3`), and run it.

Watch the health check step. If it fails, do not consider the hotfix
deployed — investigate immediately.

---

## 7. Backport the fix to `staging` and `develop`

This is the step people skip under pressure, and it's the one your
regression next sprint depends on. Without it, the next normal release from
`staging` will silently undo your hotfix.

```bash
# Backport to staging
git checkout staging
git pull origin staging
git merge main --no-edit
git push origin staging
```

```bash
# Backport to develop
git checkout develop
git pull origin develop
git merge main --no-edit
git push origin develop
```

If either merge conflicts, resolve manually — don't skip it and don't force-push over it.

---

## 8. Clean up

```bash
git branch -d hotfix/payment-timeout
git push origin --delete hotfix/payment-timeout
```

---

## 9. Post-incident

Per the Rollback Strategy and Incident Response standards: document what
happened, why it needed a hotfix instead of the normal path, and whether
anything in CI/testing should have caught it earlier. This isn't
bureaucracy — it's the only mechanism that reduces how often you need this
runbook.

---

## Quick reference

```text
main (production)
  │
  ├── hotfix/<name>  ── PR ──▶  main  ──▶  build-production.yml (auto)
  │                                              │
  │                                    git tag v1.4.3 (manual, PATCH bump)
  │                                              │
  │                                    tag-release.yml (auto on tag push,
  │                                       re-labels image, no rebuild)
  │                                              │
  │                                   deploy-production.yml (manual trigger)
  │
  └── after confirmed stable: merge main → staging, main → develop
```
