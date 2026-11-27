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
