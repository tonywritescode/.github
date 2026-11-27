# tonywritescode/.github

Shared GitHub Actions workflows for the **tonywritescode** organization.

## `reusable-grok-pr-review.yml`

Hive-backed Grok review gate for pull requests.

1. Fetches bounded graph context from `https://hive.tony.codes/api/review-context`
2. Sends that JSON + the PR diff to Grok
3. Posts a PR COMMENT review
4. **Fails the check** when Grok reports bugs

### Caller (add to each repo)

```yaml
# .github/workflows/grok-pr-review.yml
name: Grok PR review

on:
  pull_request:
    branches: [main]
    types: [opened, synchronize, reopened, ready_for_review]

concurrency:
  group: grok-review-${{ github.repository }}-${{ github.event.pull_request.number }}
  cancel-in-progress: true

permissions:
  contents: read
  pull-requests: write

jobs:
  grok-review:
    uses: tonywritescode/.github/.github/workflows/reusable-grok-pr-review.yml@main
    secrets: inherit
    with:
      # Fork PRs: prefer ubuntu. Same-repo: Mac self-hosted.
      runs_on: ${{ github.event.pull_request.head.repo.full_name == github.repository && (vars.RUNS_ON || '["self-hosted","tony-mac"]') || '"ubuntu-latest"' }}
```

See `examples/grok-pr-review.yml` for a ready-to-copy file.

### Secrets (org-level recommended)

| Secret | Purpose |
|---|---|
| `XAI_API_KEY` (or `GROK_API_KEY`) | xAI chat completions |
| `HIVE_API_KEY` (or `ARC_REVIEW_KEY`) | Company-scoped Hive key (`Bearer arc_…`) |

Set these as **organization secrets** with visibility **All repositories** (or explicitly include each consumer).

Callers should pass secrets by name (not only `secrets: inherit`) so named `workflow_call` secrets are populated:

```yaml
secrets:
  XAI_API_KEY: ${{ secrets.XAI_API_KEY }}
  GROK_API_KEY: ${{ secrets.GROK_API_KEY }}
  HIVE_API_KEY: ${{ secrets.HIVE_API_KEY }}
  ARC_REVIEW_KEY: ${{ secrets.ARC_REVIEW_KEY }}
```

### Optional repository variables

| Variable | Effect |
|---|---|
| `GROK_PR_REVIEW_ENABLED=false` | Skip the gate |
| `GROK_PR_REVIEW_ALLOW_WITHOUT_HIVE=true` | Emergency bypass if Hive is down |
| `RUNS_ON` | Override runner JSON (e.g. `'"ubuntu-latest"'`) |

### Inputs

| Input | Default | Meaning |
|---|---|---|
| `runs_on` | `["self-hosted","tony-mac"]` | JSON `runs-on` value |
| `scripts_ref` | `main` | Ref of this repo for the Python review scripts |
| `hive_repository` | _(empty)_ | Hive scope override when GitHub owner ≠ indexed owner (e.g. `tonycodes/gitdocs`) |

## Access

Repositories that call this reusable workflow must allow it under  
**Settings → Actions → General → Access** on `tonywritescode/.github`  
(set to “Accessible from repositories in the `tonywritescode` organization”).

### Hive indexing during the org move

If `GITHUB_REPOSITORY` is `tonywritescode/<name>` and Hive still indexes
`tonycodes/<name>`, the script tries that fallback automatically. You can also
set `with.hive_repository` explicitly. Index the repo under the new owner in Hive
when the move is permanent.

## Available Workflows

### `reusable-ci.yml` — PR Quality Gate

Runs typecheck, lint, and tests in parallel on pull requests.

```yaml
# .github/workflows/ci.yml
name: CI
on:
  pull_request:
    branches: [main]
jobs:
  ci:
    uses: tonywritescode/.github/.github/workflows/reusable-ci.yml@main
    with:
      has_prisma: true
      has_client: true
```

**Inputs:** `runs_on`, `node_version`, `has_prisma`, `has_client`, `has_mcp`

`setup-node` enables Actions `cache: npm` only on GitHub-hosted runners. Self-hosted
(Mac) skips it — that cache path often downloads ~2GB then fails auth mid-restore.

### `reusable-deploy.yml` — Production Deploy

Builds Docker image on VPS and deploys via Docker Swarm.

```yaml
# .github/workflows/deploy.yml (partial)
jobs:
  deploy:
    uses: tonywritescode/.github/.github/workflows/reusable-deploy.yml@main
    with:
      app_name: my-app
      prod_domain: my-app.com
      migration_command: 'npx prisma migrate deploy'
    secrets: inherit
```

**Inputs:** `app_name`, `prod_domain`, `vps_host`, `network`, `migration_command`, `seed_command`, `worker_name`, `worker_command`, `vite_env_from_swarm`, `build_args`, `post_deploy_script`, `health_endpoint`, `docker_volumes`

### `cursor-agent-dispatch.yml` — Cursor cloud agent

Launches a Cursor cloud agent for `issues` opened and for pull requests that are opened as non-drafts or marked ready for review, so calling repositories do not need a polling agent. The workflow is `workflow_call` and reads `github.event` from the caller. Optional input `max_launches_per_hour` defaults to 5.

For every caller, dispatch is off unless the repo variable is set to 'on' (`CURSOR_AGENT_DISPATCH`). GitHub's `==` comparison is case-insensitive, so `On` and `ON` enable dispatch too. Any other value, including an unset variable, stays off. This repository does not set that variable from CI.

The agent runs when the author is `tonycodes`, or the item has the `agent-ok` label. Authors other than `tonycodes` get a plan comment only, with no code changes. It skips forks, bot authors, draft pull requests that were just opened, pull request head branches that start with `cursor/`, API-created issues, bulk-imported issues, items that already have `agent-started`, and repositories that already hit the hourly launch cap. Each launch uses a deterministic id from the repository and the issue or pull request number, so a retry does not start a second agent. On a launch it creates `agent-started` with `--force` if needed and adds it. If the Cursor API call fails, it removes that label so a rerun can try again.

An opened issue from `tonycodes` gets a test-first fix: failing test first, then the change that makes it pass, then a pull request for the normal gates (dev tests, PO after-green review, QA G3). A non-draft pull request from `tonycodes`, including one marked ready for review, gets review comments only. That agent is told not to push. Every prompt forbids deploys, releases, workflow edits, ruleset edits, secret edits, opening issues, and starting further agents.

`CURSOR_API_KEY` is required to launch an agent. Pass it explicitly. The workflow masks the key and sends it only in an `Authorization: Bearer` header. A launch without the key fails. Pin the workflow by the full commit SHA below. That SHA is the commit that contains this dispatcher.

```yaml
name: Cursor Agent

on:
  issues:
    types: [opened]
  pull_request:
    types: [opened, ready_for_review]

permissions:
  contents: read
  issues: write
  pull-requests: write

jobs:
  dispatch:
    uses: tonywritescode/.github/.github/workflows/cursor-agent-dispatch.yml@33d4473de9080f2df50427ce34f2e42c7843763f
    secrets:
      CURSOR_API_KEY: ${{ secrets.CURSOR_API_KEY }}
```

The launch call is `POST https://api.cursor.com/v1/agents`. That is the current Create Agent endpoint in the [Cloud Agents API](https://cursor.com/docs/cloud-agent/api/endpoints). Authentication is the bearer header described in the [Cursor APIs overview](https://cursor.com/docs/api). `POST /v0/agents` is the legacy surface and is not called.

### `reusable-release.yml` — Semantic Versioning

Auto-creates tags and GitHub releases using semantic-release after successful deploy.

```yaml
# .github/workflows/deploy.yml (partial)
jobs:
  release:
    needs: deploy
    uses: tonywritescode/.github/.github/workflows/reusable-release.yml@main
    permissions:
      contents: write
    secrets: inherit
```

## Adding to a New Repo

1. Create `.github/workflows/ci.yml` and `.github/workflows/deploy.yml` (see examples above)
2. Add `.releaserc.json` (copy `releaserc-template.json`)
3. Add `semantic-release` to devDependencies: `npm i -D semantic-release`
4. Use conventional commits: `feat:`, `fix:`, `BREAKING CHANGE:`
