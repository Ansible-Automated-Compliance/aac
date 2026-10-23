# Releasing AAC

**Version:** v1.1
**Date:** 2026-08-29
**Authors:** Tim Coulter (Red Hat) with Claude (Anthropic)

## Why this exists

A customer asked, after a rough install, whether AAC was "a proper solution with
change controls and release management." At the time the honest answer was no:
two releases existed, both from before May, with tag names that described
neither the version nor each other, no changelog, and no version recorded
anywhere in the tree. 257 pull requests had merged to `main` since the last one.
Nobody — not the customer, not the field, not the maintainer — could say which
build was installed anywhere.

This document is the smallest thing that makes "you are running v2.8.0" a
sentence someone can say and verify.

It does not make AAC a supported product. It makes it a versioned one.

---

## Versioning

`MAJOR.MINOR.PATCH`, tagged `vMAJOR.MINOR.PATCH`.

**AAC is on the `2.x` lineage.** That is the numbering `CHANGELOG.md` and
`CLAUDE.md` have used since 2.0.0 (2025-12-01). Two GitHub releases used an
unrelated `0.x` scheme and were never reconciled with it; from 2.8.0 the `2.x`
line is authoritative and the `0.x` releases are left as historical artifacts.
Do not start a third scheme.

A high major version is not a maturity claim here. The policy content is well
tested; the playbooks and installers are a reference implementation. See
`docs/AAC_HONEST_STATUS_AND_POSITIONING.md` for what is and is not supported --
the version number says nothing about that and should not be quoted as if it did.

| Bump | When |
|---|---|
| **MAJOR** | A change that breaks an existing deployment's config contract, schema, or documented entry points with no compatibility path. Rare. |
| **MINOR** | New frameworks, demos, collections or install capability. Also breaking changes that ship with a documented upgrade step. |
| **PATCH** | Fixes and documentation only. No new capability, no schema change, no config contract change. |

The current version lives in `VERSION`, one line, no prefix. It is the single
source of truth; anything that needs to display a version reads that file rather
than carrying its own copy. `CLAUDE.md` points at it rather than restating it,
because a second copy is a second thing to forget.

---

## What a release must satisfy

Do not cut a release unless all of these hold. Each is checkable, and each
exists because it failed at least once.

1. **CI is green on `main`.** All workflows, not just the one you were watching.
2. **The gate output is real, not just green.** Read the step logs and confirm
   the counts are plausible — files parsed, playbooks checked, files scanned. A
   gate in this repository once reported "checked 221 files" in 2.7 seconds
   while running nothing at all. Every gate now carries a tripwire that fails on
   an implausibly low count; confirm the tripwire did not fire and the number
   looks right.
3. **`./scripts/validate_playbooks.sh` exits 0.** *Currently it does not* — see
   the known limitation in the changelog. Until the three broken roles are
   resolved, record the exact failure in the release notes rather than pretending
   it passes.
4. **The policy submodule is pinned at a merged commit on the library's `main`,**
   not a branch tip or a local commit. Verify:
   ```bash
   # Initialize and refresh first: on a fresh clone the submodule may be absent,
   # and on a stale one the remote refs can be old enough to give a wrong answer.
   git submodule update --init --recursive
   git -C policies fetch --quiet origin

   PINNED=$(git ls-tree HEAD policies | awk '{print $3}')
   git -C policies branch -r --contains "$PINNED" 2>/dev/null | grep -q 'origin/main' \
     && echo "OK: pinned commit is on library main" \
     || echo "STOP: pinned commit is not merged upstream"
   ```
5. **A fresh clone can be configured.** From a clean checkout,
   `./scripts/aac-configure.sh` creates the three config files and the preflight
   playbook runs far enough to report what is missing.
6. **`CHANGELOG.md` has an entry for this version,** including a **Known
   limitations** section. A release note that lists only wins is not a record.
7. **No open PR is waiting to go into this release.** Either merge it or accept
   it slips.

---

## Cutting the release

```bash
# 1. Start from a clean, current main.
git checkout main && git pull origin main
git status --porcelain          # must be empty

# 2. Bump the version and write the changelog entry on a branch.
git checkout -b chore/release-v2.9.0
echo '2.9.0' > VERSION
$EDITOR CHANGELOG.md            # move [Unreleased] -> [2.9.0] — YYYY-MM-DD,
                                # then leave a fresh empty [Unreleased] behind
git commit -am "chore(release): v2.9.0"
gh pr create --title "chore(release): v2.9.0" --body "..."

# 3. Merge it once CI is green, then tag the merge commit on main.
git checkout main && git pull origin main
git tag -a v2.9.0 -m "AAC v2.9.0"
git push origin v2.9.0

# 4. Extract this version's changelog section and publish with it as the body.
#    scripts/changelog_section.py prints one version's entry to stdout.
python3 scripts/changelog_section.py 2.9.0 > /tmp/relnotes.md
gh release create v2.9.0 --title "AAC v2.9.0" --notes-file /tmp/relnotes.md
```

**Tag the commit that is on `main`,** not the branch head before merge. Squash
merges rewrite the commit, so a tag made before merging points at an object that
is not in the released history.

---

## What a release is not

- **Not a support commitment.** See `docs/AAC_HONEST_STATUS_AND_POSITIONING.md`.
  AAP Policy as Code is a supported Red Hat product feature; AAC's policy content
  and installers are not, and tagging does not change that.
- **Not a promise the delivery layer is production-ready.** It is a promise that
  a specific set of bytes has a name.
- **Not a substitute for testing.** The gates check structure — that files parse,
  that templates render, that no credential or foreign address ships. They do
  not check that a playbook does the right thing.

---

## If you have to ship a fix fast

Cut a PATCH from `main` the same way. Do not tag from a hotfix branch, do not
skip the changelog entry, and do not skip step 2 above — reading the gate output
is the step most likely to be dropped under time pressure, and it is the one
that has caught the most.

If the fix cannot wait for CI, say so in the release notes. An honest record of
a rushed release is worth more than a tidy one that hides it.

---

## Revision history

| Version | Date | Change |
|---|---|---|
| v1.0 | 2026-08-29 | First release process. Written after a customer asked whether AAC had change controls and the honest answer was no. |
| **v1.1** | 2026-08-29 | Corrected before first real use. The versioning section had argued for a `0.x` lineage; that was based on the GitHub release titles rather than on `CHANGELOG.md`, which has tracked `2.x` since 2.0.0. Now states that `2.x` is authoritative and that a third scheme must not be started. Also made two snippets actually runnable: the release-notes step used `--notes-file <(...)`, which is not a command, and the submodule check assumed an initialized submodule with fresh refs. |
