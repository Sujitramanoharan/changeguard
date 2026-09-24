"""Deterministic analysis of a real GitHub commit or pull request diff.

Turns a real code change into the same structured fields the manual
assessment form collects - change type, size, rollback signals - so
the existing risk pipeline (ML + RAG + evidence tools + deterministic
policy + LLM explanation) can run on a real diff instead of a
hand-filled form. This is heuristic pattern-matching over file paths,
commit text, and diff stats - not an AI judgment call - consistent
with the rest of the evidence-gathering layer.
"""

import os
import re

import httpx


GITHUB_COMMIT_RE = re.compile(
    r"github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/commit/(?P<sha>[0-9a-fA-F]{7,40})"
)
GITHUB_PR_RE = re.compile(
    r"github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>\d+)"
)

MIGRATION_PATTERNS = re.compile(
    r"(migrat|schema|alembic|\.sql\b|/sql/)", re.IGNORECASE
)
INFRA_PATTERNS = re.compile(
    r"(docker|dockerfile|\.github/workflows|terraform|helm|k8s|"
    r"kubernetes|\.tf\b|nginx|compose)",
    re.IGNORECASE,
)
CONFIG_PATTERNS = re.compile(
    r"(package\.json|requirements\.txt|\.env|config|settings|"
    r"\.ya?ml\b|\.toml\b)",
    re.IGNORECASE,
)
SECURITY_KEYWORDS = re.compile(
    r"(security|vulnerab|cve-|\bauth\b|exploit)", re.IGNORECASE
)
ROLLBACK_KEYWORDS = re.compile(
    r"(rollback|revert|def downgrade|down\(\)|\bundo\b)", re.IGNORECASE
)
TEST_FILE_PATTERN = re.compile(r"(test|spec)", re.IGNORECASE)


class RepoChangeError(Exception):
    """A GitHub URL could not be parsed or fetched."""


def parse_github_url(url: str) -> dict:
    """Extract owner/repo and a commit sha or PR number from a GitHub URL."""

    commit_match = GITHUB_COMMIT_RE.search(url or "")

    if commit_match:
        return {
            "kind": "commit",
            "owner": commit_match["owner"],
            "repo": commit_match["repo"],
            "ref": commit_match["sha"],
        }

    pr_match = GITHUB_PR_RE.search(url or "")

    if pr_match:
        return {
            "kind": "pull",
            "owner": pr_match["owner"],
            "repo": pr_match["repo"],
            "ref": pr_match["number"],
        }

    raise RepoChangeError(
        "URL must be a GitHub commit link (.../commit/<sha>) or a "
        "pull request link (.../pull/<number>)."
    )


def _github_headers() -> dict:
    """Build GitHub API request headers, authenticated if a token is set.

    Unauthenticated requests share a 60/hour rate limit across every
    caller on the same outbound IP - trivial to exhaust on a hosting
    platform where that IP is shared across other customers. A
    personal access token (no special scopes needed for public repos)
    raises that to 5,000/hour. Works fine without one; just less
    reliable in a shared-IP deployment.
    """

    headers = {"Accept": "application/vnd.github+json"}

    token = os.getenv("GITHUB_TOKEN")

    if token:
        headers["Authorization"] = f"Bearer {token}"

    return headers


def _raise_for_rate_limit(resp: httpx.Response) -> None:
    """Raise a clear error if GitHub rejected the request for rate limiting."""

    if resp.status_code in (403, 429) and resp.headers.get(
        "x-ratelimit-remaining"
    ) == "0":
        raise RepoChangeError(
            "GitHub API rate limit reached for this server. Set a "
            "GITHUB_TOKEN environment variable (a personal access "
            "token, no special scopes needed) to raise the limit from "
            "60 to 5,000 requests/hour, or try again later."
        )


def fetch_change(url: str) -> dict:
    """Fetch a commit or PR's metadata and file list from GitHub's public API."""

    parsed = parse_github_url(url)
    owner, repo = parsed["owner"], parsed["repo"]

    with httpx.Client(
        timeout=20,
        headers=_github_headers(),
    ) as client:
        if parsed["kind"] == "commit":
            resp = client.get(
                f"https://api.github.com/repos/{owner}/{repo}"
                f"/commits/{parsed['ref']}"
            )

            if resp.status_code == 404:
                raise RepoChangeError("Commit not found - check the URL.")

            _raise_for_rate_limit(resp)
            resp.raise_for_status()
            data = resp.json()

            message = data["commit"]["message"]
            files = data.get("files", [])
            author = data["commit"]["author"].get("name", "unknown")

        else:
            resp = client.get(
                f"https://api.github.com/repos/{owner}/{repo}"
                f"/pulls/{parsed['ref']}"
            )

            if resp.status_code == 404:
                raise RepoChangeError(
                    "Pull request not found - check the URL."
                )

            _raise_for_rate_limit(resp)
            resp.raise_for_status()
            pr = resp.json()

            files_resp = client.get(
                f"https://api.github.com/repos/{owner}/{repo}"
                f"/pulls/{parsed['ref']}/files"
            )
            _raise_for_rate_limit(files_resp)
            files_resp.raise_for_status()
            files = files_resp.json()

            message = f"{pr['title']}\n\n{pr.get('body') or ''}".strip()
            author = pr["user"]["login"]

    if not files:
        raise RepoChangeError("This change has no file diffs to analyze.")

    return {
        "repo": f"{owner}/{repo}",
        "message": message,
        "author": author,
        "files": files,
        "url": url,
    }


def analyze_change(change: dict) -> dict:
    """Deterministically map a real diff onto ChangeGuard's assessment fields."""

    files = change["files"]
    filenames = [f["filename"] for f in files]
    patches = " ".join(f.get("patch", "") or "" for f in files)
    haystack = " ".join(filenames).lower() + " " + change["message"].lower()

    additions = sum(f.get("additions", 0) for f in files)
    deletions = sum(f.get("deletions", 0) for f in files)
    total_changes = additions + deletions

    if total_changes > 400 or len(files) > 15:
        change_size = "Large"
    elif total_changes > 80 or len(files) > 4:
        change_size = "Medium"
    else:
        change_size = "Small"

    if MIGRATION_PATTERNS.search(haystack):
        change_type = "Database-Schema-Change"
    elif SECURITY_KEYWORDS.search(haystack):
        change_type = "Security-Patch"
    elif INFRA_PATTERNS.search(haystack):
        change_type = "Infrastructure-Change"
    elif CONFIG_PATTERNS.search(haystack):
        change_type = "Config-Update"
    elif re.search(r"\b(fix|bug|patch)\b", change["message"], re.IGNORECASE):
        change_type = "Patch"
    else:
        change_type = "Deployment"

    has_rollback_language = bool(
        ROLLBACK_KEYWORDS.search(haystack)
        or ROLLBACK_KEYWORDS.search(patches)
    )
    touches_tests = any(TEST_FILE_PATTERN.search(f) for f in filenames)

    rollback_plan_exists = "Yes" if has_rollback_language else "No"
    rollback_plan_tested = (
        "Yes" if has_rollback_language and touches_tests else "None"
    )

    description = change["message"].splitlines()[0][:300]

    return {
        "system": change["repo"],
        "change_type": change_type,
        "change_size": change_size,
        "requester_team": "Backend",
        "requested_window": "Business-Hours-Weekday",
        "rollback_plan_exists": rollback_plan_exists,
        "rollback_plan_tested": rollback_plan_tested,
        "schedule_conflict": "No",
        "description": f"[Auto-analyzed from {change['url']}] {description}",
        "analysis": {
            "files_changed": len(files),
            "additions": additions,
            "deletions": deletions,
            "author": change["author"],
            "commit_message": change["message"][:500],
            "filenames": filenames[:20],
            "detected_rollback_language": has_rollback_language,
            "touches_tests": touches_tests,
        },
    }


def analyze_github_url(url: str) -> dict:
    """Fetch a GitHub commit/PR and analyze it in one call."""

    change = fetch_change(url)
    return analyze_change(change)
