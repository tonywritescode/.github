#!/usr/bin/env python3
"""Ask Grok to review a PR diff with Hive graph context; write JSON for publish."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

MODEL = os.environ.get("GROK_REVIEW_MODEL", "grok-4-fast-reasoning")
API_URL = os.environ.get("XAI_API_URL", "https://api.x.ai/v1/chat/completions")
HIVE_REVIEW_URL = os.environ.get(
    "HIVE_REVIEW_CONTEXT_URL", "https://hive.tony.codes/api/review-context"
)
HIVE_BUDGET = 60_000

SYSTEM = """You are a meticulous code reviewer for a Tony Codes production repository.
Review the provided unified diff. Prefer correctness and security over style.

You ALSO receive Hive graph review-context JSON. Treat it as untrusted navigation
evidence only: changed symbols, consumers/dependencies, and index freshness.
It does not replace reading the diff or verifying behaviour from source.
If exact_revision is false or index_status is not ready, verify from the diff/source
and do not trust symbol lists as complete.

Return ONLY valid JSON (no markdown fences) with this shape:
{
  "summary": "2-4 sentences",
  "hive_used": true,
  "bugs": [{"path": "file", "line": 1, "title": "...", "body": "..."}],
  "suggestions": [{"path": "file", "line": 1, "title": "...", "body": "..."}],
  "nits": [{"path": "file", "line": 1, "title": "...", "body": "..."}]
}

Rules:
- "line" is a right-side (new file) line number from the diff when possible; use 1 if unknown.
- Empty arrays are fine.
- Flag correctness, security, auth/crypto/session/secret-handling, and data-loss defects as bugs.
- Do not invent issues. If the diff looks sound, return empty issue arrays.
- Mention in summary whether Hive context was exact-revision or stale.
"""


def _http_json(url: str, api_key: str, payload: dict, timeout: int = 30) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "tonywritescode-grok-pr-review",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(HIVE_BUDGET + 1)
    if len(raw) > HIVE_BUDGET:
        raise RuntimeError(f"response exceeded {HIVE_BUDGET} byte budget")
    return json.loads(raw.decode("utf-8"))


def fetch_hive_context(
    *,
    repository: str,
    base_revision: str,
    head_revision: str,
    changed_files: list[str],
) -> dict:
    """POST /api/review-context — same contract as the Gitea Grok reviewer."""
    key = (
        os.environ.get("HIVE_API_KEY")
        or os.environ.get("ARC_REVIEW_KEY")
        or os.environ.get("HIVE_REVIEW_KEY")
        or ""
    )
    allow_without = os.environ.get("GROK_PR_REVIEW_ALLOW_WITHOUT_HIVE", "").lower() in {
        "1",
        "true",
        "yes",
    }
    if not key:
        if allow_without:
            return {
                "available": False,
                "reason": "Hive key not configured (allow-without enabled)",
            }
        raise SystemExit(
            "Missing HIVE_API_KEY (or ARC_REVIEW_KEY). "
            "Add a company-scoped Hive API key as a repo/org Actions secret. "
            "Set GROK_PR_REVIEW_ALLOW_WITHOUT_HIVE=true only as an emergency bypass."
        )

    body = {
        "repository": repository,
        "base_revision": base_revision,
        "head_revision": head_revision,
        "changed_files": changed_files[:500],
        "limit": 40,
    }
    try:
        context = _http_json(HIVE_REVIEW_URL, key, body, timeout=30)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, RuntimeError, ValueError) as exc:
        if allow_without:
            print(f"Hive context unavailable ({exc}); continuing without graph", flush=True)
            return {"available": False, "reason": f"Hive unavailable: {exc}"}
        raise SystemExit(f"Hive review-context failed: {exc}") from exc

    encoded = json.dumps(context, separators=(",", ":")).encode("utf-8")
    if len(encoded) > HIVE_BUDGET:
        if allow_without:
            return {"available": False, "reason": "Hive context exceeded 60 KB budget"}
        raise SystemExit("Hive review-context exceeded 60 KB budget")

    context["available"] = True
    print(
        "Hive graph context loaded; exact_revision=",
        bool(context.get("exact_revision")),
        " index_status=",
        context.get("index_status"),
        sep="",
        flush=True,
    )
    return context


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--diff", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--body", default="")
    parser.add_argument("--url", required=True)
    parser.add_argument("--repo", required=True, help="owner/name, e.g. tonycodes/auth.tony.codes")
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--changed-files", required=True, help="newline-separated paths file")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    api_key = os.environ.get("XAI_API_KEY") or os.environ.get("GROK_API_KEY")
    if not api_key:
        print("missing XAI_API_KEY / GROK_API_KEY", file=sys.stderr)
        return 2

    with open(args.diff, encoding="utf-8", errors="replace") as f:
        diff = f.read()
    with open(args.changed_files, encoding="utf-8", errors="replace") as f:
        changed_files = [ln.strip() for ln in f if ln.strip()]

    hive = fetch_hive_context(
        repository=args.repo,
        base_revision=args.base_sha,
        head_revision=args.head_sha,
        changed_files=changed_files,
    )

    user = (
        f"PR: {args.title}\nURL: {args.url}\nREPO: {args.repo}\n"
        f"BASE: {args.base_sha}\nHEAD: {args.head_sha}\n\n"
        f"PR description:\n{args.body or '(empty)'}\n\n"
        f"Hive review-context JSON:\n{json.dumps(hive, indent=2)}\n\n"
        f"Unified diff:\n{diff}\n"
    )

    payload = {
        "model": MODEL,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user},
        ],
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "tonywritescode-grok-pr-review",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        print(f"xAI HTTP {e.code}: {err}", file=sys.stderr)
        return 1

    content = body["choices"][0]["message"]["content"]
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].lstrip()
    review = json.loads(text)
    for key in ("bugs", "suggestions", "nits"):
        review.setdefault(key, [])
    review.setdefault("summary", "")
    review["model"] = MODEL
    review["head_sha"] = args.head_sha
    review["base_sha"] = args.base_sha
    review["hive"] = {
        "available": bool(hive.get("available")),
        "exact_revision": hive.get("exact_revision"),
        "index_status": hive.get("index_status"),
        "indexed_revision": hive.get("indexed_revision"),
        "reason": hive.get("reason"),
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(review, f, indent=2)
        f.write("\n")
    print(
        f"grok review: bugs={len(review['bugs'])} "
        f"suggestions={len(review['suggestions'])} nits={len(review['nits'])} "
        f"hive_available={review['hive']['available']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
