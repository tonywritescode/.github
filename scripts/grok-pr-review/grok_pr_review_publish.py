#!/usr/bin/env python3
"""Publish a Grok review JSON as a GitHub PR COMMENT and fail on bugs."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys


def gh_api(repo: str, method: str, path: str, payload: dict) -> dict:
    cmd = [
        "gh",
        "api",
        f"repos/{repo}{path}",
        "-X",
        method,
        "--input",
        "-",
    ]
    proc = subprocess.run(
        cmd,
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr.decode("utf-8", errors="replace"))
        raise SystemExit(proc.returncode)
    return json.loads(proc.stdout.decode("utf-8") or "{}")


def fmt_issue(sev: str, item: dict) -> str:
    path = item.get("path") or "unknown"
    line = item.get("line") or 1
    title = item.get("title") or "finding"
    body = item.get("body") or ""
    return f"**[{sev}]** `{path}:{line}` — {title}\n\n{body}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--review", required=True)
    args = parser.parse_args()

    with open(args.review, encoding="utf-8") as f:
        review = json.load(f)

    bugs = review.get("bugs") or []
    suggestions = review.get("suggestions") or []
    nits = review.get("nits") or []

    hive = review.get("hive") or {}
    hive_line = (
        f"_Hive: available={hive.get('available')} exact_revision={hive.get('exact_revision')} "
        f"index_status={hive.get('index_status')} indexed={hive.get('indexed_revision')}_"
    )
    if hive.get("reason"):
        hive_line += f"\n_Hive note: {hive.get('reason')}_"

    sections = [
        "## Grok + Hive review",
        "",
        review.get("summary") or "(no summary)",
        "",
        f"_model: `{review.get('model', 'unknown')}` · head `{args.head_sha[:12]}`_",
        hive_line,
        "",
        "### Issue counts",
        f"- bugs: {len(bugs)}",
        f"- suggestions: {len(suggestions)}",
        f"- nits: {len(nits)}",
    ]
    if bugs:
        sections += ["", "### Bugs"]
        sections += [fmt_issue("bug", i) for i in bugs]
    if suggestions:
        sections += ["", "### Suggestions"]
        sections += [fmt_issue("suggestion", i) for i in suggestions]
    if nits:
        sections += ["", "### Nits"]
        sections += [fmt_issue("nit", i) for i in nits]

    # Inline comments only when path+line look usable; otherwise body-only.
    comments = []
    for sev, items in (("bug", bugs), ("suggestion", suggestions), ("nit", nits)):
        for item in items:
            path = item.get("path")
            line = item.get("line")
            if not path or not isinstance(line, int) or line < 1:
                continue
            comments.append(
                {
                    "path": path,
                    "line": line,
                    "side": "RIGHT",
                    "body": fmt_issue(sev, item),
                }
            )

    payload = {
        "commit_id": args.head_sha,
        "event": "COMMENT",
        "body": "\n".join(sections),
        # Prefer body-only if too many speculative lines; GitHub 422s on bad lines.
        "comments": comments[:20],
    }

    try:
        result = gh_api(args.repo, "POST", f"/pulls/{args.pr}/reviews", payload)
        print(f"posted review id={result.get('id')} state={result.get('state')}")
    except SystemExit:
        # Retry body-only when inline positions are rejected.
        payload["comments"] = []
        result = gh_api(args.repo, "POST", f"/pulls/{args.pr}/reviews", payload)
        print(f"posted body-only review id={result.get('id')} state={result.get('state')}")

    if bugs:
        print(f"::error::Grok reported {len(bugs)} bug(s) — failing the review gate")
        return 1
    print("Grok review gate passed (no bugs)")
    return 0


if __name__ == "__main__":
    # Ensure token is visible to gh
    if not os.environ.get("GH_TOKEN") and os.environ.get("GITHUB_TOKEN"):
        os.environ["GH_TOKEN"] = os.environ["GITHUB_TOKEN"]
    raise SystemExit(main())
