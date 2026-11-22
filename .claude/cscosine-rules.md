## cscosine rules

The rules of every cscosine repository, for people and agents. This file is owned by the project template
(`cscosine/cs-project-template`) and is the same in every repository: change it there, then `copier update`. What is
specific to this repository is in `AGENTS.md`.

### The organisation

- **Outer** repositories run CI and release: the tools (csCMake, csorchestrator, csWiki), the distributions
  (third_party_base_libs, csqt6, csopencvcpu, csopencvcuda, csfoundation, csoptimization) and the applications
  (csImgTracker, csSkiTracker).
- **Inner** repositories are built by an outer one and have no build CI of their own: the first-party libraries
  (csCore, csLie, csCamera, csVisOpenGL by csfoundation; csNelson, csBlockMatrix by csoptimization) and the forks of
  third-party libraries (by third_party_base_libs, csopencvcpu, csopencvcuda). A change in an inner repository is
  validated by its outer repository's CI.
- Checks: every repository on the template runs `.github/workflows/checks.yml` (pre-commit on every file, every hook,
  in the project venv) on each push and PR to `main`, inner repositories included.
- Release chain (a change travels in this order): csorchestrator, csCMake → third_party_base_libs → csqt6,
  csopencvcpu, csopencvcuda → csfoundation → csoptimization → applications.
- Plans and their progress: `cscosine/.github/plans/`. A commit or PR that completes a plan step names the step id
  (e.g. `S1b`) in its body.

### Working with the user

- Leave every change unstaged for review; never stage on your own. Stop and summarise after each step.
- Commit only when the user says so (then `git add -A` and commit); push only when asked.
- One commit (at least) per step; a commit message says what and why, its first line on its own.
- Do not run the CI matrix locally: one host build is enough; the user runs CI on GitHub.
- Ask before anything that cannot be undone or is seen by others: deleting branches, tags or releases, force pushes,
  changing repository visibility or settings, publishing.
- Never propose pull requests or issues to third-party (upstream) projects on your own: a fix of a fork stays a commit
  of ours on the fork; contributing it upstream is the user's decision, case by case.

### Branches and pull requests

The commands for each case: [CONTRIBUTING.md](https://github.com/cscosine/.github/blob/main/CONTRIBUTING.md).

| Branch | Where | Meaning | How it moves |
|---|---|---|---|
| `main` | every repository (default branch) | The trunk: the latest work, kept green | Direct commits; `feature/*` / `fix/*` merged in; never force pushed (forks: rebased on an upstream sync) or deleted |
| `stable` | outer repositories | The last final release | Only fast-forwarded to a final release tag (`git push origin vX.Y.Z:stable`) |
| `feature/<topic>`, `fix/<topic>` | any | Work in progress, also on the inner repositories of a change (same name) | Free; CI on demand (`gh workflow run <workflow> --ref feature/<topic>`); deleted after the merge |
| `cpu`, `cuda` | the opencv fork | `main` (the common stack) plus the setup of the variant | Rebased on `main` |

- Enforced by GitHub: no force push or deletion of `main` / `stable` (forks: no deletion), final tags never moved or
  deleted. Everything else (a feature branch, waiting for CI before a tag, a release candidate first, PRs) is good
  practice, skipped when in a hurry: a one-line fix can be committed, tagged and released in one build.
- Builds: on `main` and on tags; the weekly schedule on `main` (inner changes and runner-image changes); a feature
  branch on demand. No build for `stable` (it only receives commits already built).
- The weekly schedule is a queue in dependency order, one project at a time (no shared runners), in CET: Sunday 20:00
  cs-pre-commit-hooks and the template, 20:15 the tools (csCMake, csorchestrator, csWiki), 20:50 csqt6, then from Monday
  01:15 the build train, the `.github` ecosystem update at 07:00 (08:00 in summer: the crons are UTC). A new outer
  project gets its own slot after the projects it depends on (`schedule=` in its recipe, crons in UTC), never
  csorchestrator's default (Monday 03:00 UTC). The queue: ECOSYSTEM.md, Weekly queue.

### Changes across repositories

1. The same branch name, `feature/<topic>`, in every repository touched.
2. The outer recipe on its `feature/<topic>` points to the inner `feature/<topic>` (one line); CI on demand.
3. Merged into `main` in the release-chain order (inner first, then the outer recipe back to `main`), each `main` green
   before the next.

### Releases and tags

- Release candidate: tag `vX.Y.Z-rcN` on a commit of `main` (a pre-release, consumed by the other repositories).
- Release: tag `vX.Y.Z` on the commit (usually the last rc), then `stable` fast-forwarded to it. The libraries and
  forks it built are tagged on the commits used (own semver; forks `-cs.N`).
- Forks: `vX.Y.Z-cs.N` (upstream version, our patch level); our changes are commits on top of the upstream tag.
- Versions: the first commit that changes a repository after a release bumps its version (`pyproject.toml` or
  `project(VERSION)`), by semver (from 1.0.0 major / minor / patch = breaking / feature / fix; in 0.x minor = breaking,
  patch = the rest); details and exceptions: CONTRIBUTING.md, "Versions".
- Stable tags (`vX.Y.Z`, `vX.Y.Z-cs.N`) are never moved or deleted. Pre-release tags (`-rcN`, `-test…`) can be
  deleted (with their release: `gh release delete <tag> --cleanup-tag`) but never moved: a broken rc gets the next
  number.
- Recipes name their refs: inner repositories at `main` (or a `feature/*` while working on it), released providers by
  tag, csCMake by release. An exact rebuild of a release comes from its tags and its manifest.

### Where things belong

- Generic behaviour goes in csCMake or csorchestrator; they never contain the names of cscosine projects. What a
  library needs stays in the library; what a provider imposes on its consumers (e.g. system packages of Qt plugins) is
  declared by the provider, not repeated by each consumer.
- One concern, one place: reuse what exists (e.g. OpenMP through csCore `CS_OMP`, written indented like the statement
  it precedes, the macOS deployment target through csCMake) instead of a second mechanism.
- Generated files are never edited by hand: CI workflows (`<name>_project.py generate-github-workflow`), presets
  (`cscmake-generate-presets`), `dependencies/`. Change the source, regenerate, commit both.
- The shared files of every repository come from `cs-project-template` (who owns which file: the repository's
  `AGENTS.md`): never edit a template part in a repository; change the template, tag it, `copier update`. Formatting
  is pre-commit's (clang-format for C / C++ / CUDA, ruff for Python): never by hand.
- No hidden side effects, no deprecation steps: the ecosystem moves to a new API directly.
- Projects use released csCMake / csorchestrator; a clone of their `main` only while a change of them is in progress
  (made there, with their own rules, released as the next rc).

### Writing

- Docs, comments and READMEs describe the present only; history goes in commit messages and `CHANGELOG.md`.
- A user-visible change gets a `CHANGELOG.md` entry; a new behaviour gets a test.
