"""Unit tests for GitHub URL parsing and diff-to-change-request heuristics.

Only the pure functions (no network) are tested here - fetch_change()
itself talks to GitHub's API and is exercised manually/live instead.
"""

import pytest

from repo_change_analysis import RepoChangeError, analyze_change, parse_github_url


def test_parse_commit_url():
    parsed = parse_github_url(
        "https://github.com/octocat/Hello-World/commit/7fd1a60b01f91b314f5"
    )

    assert parsed["kind"] == "commit"
    assert parsed["owner"] == "octocat"
    assert parsed["repo"] == "Hello-World"
    assert parsed["ref"] == "7fd1a60b01f91b314f5"


def test_parse_pull_request_url():
    parsed = parse_github_url(
        "https://github.com/octocat/Hello-World/pull/42"
    )

    assert parsed["kind"] == "pull"
    assert parsed["ref"] == "42"


def test_parse_invalid_url_raises():
    with pytest.raises(RepoChangeError):
        parse_github_url("https://example.com/not-a-github-url")


def make_change(**overrides):
    change = {
        "repo": "acme/payments",
        "message": "Update dependencies",
        "author": "dev",
        "files": [{"filename": "README.md", "additions": 2, "deletions": 1}],
        "url": "https://github.com/acme/payments/commit/abc123",
    }
    change.update(overrides)
    return change


def test_migration_files_detected_as_schema_change():
    result = analyze_change(
        make_change(
            files=[
                {
                    "filename": "migrations/0012_add_column.sql",
                    "additions": 20,
                    "deletions": 0,
                }
            ]
        )
    )

    assert result["change_type"] == "Database-Schema-Change"


def test_dockerfile_change_detected_as_infrastructure():
    result = analyze_change(
        make_change(
            files=[
                {"filename": "Dockerfile", "additions": 5, "deletions": 2}
            ]
        )
    )

    assert result["change_type"] == "Infrastructure-Change"


def test_large_diff_is_sized_large():
    result = analyze_change(
        make_change(
            files=[
                {
                    "filename": f"src/file_{i}.py",
                    "additions": 30,
                    "deletions": 10,
                }
                for i in range(20)
            ]
        )
    )

    assert result["change_size"] == "Large"


def test_small_diff_is_sized_small():
    result = analyze_change(make_change())

    assert result["change_size"] == "Small"


def test_no_rollback_language_defaults_to_no():
    result = analyze_change(make_change())

    assert result["rollback_plan_exists"] == "No"
    assert result["rollback_plan_tested"] == "None"


def test_rollback_language_with_tests_marks_tested():
    result = analyze_change(
        make_change(
            message="Add revert path for the migration",
            files=[
                {
                    "filename": "migrations/0012.sql",
                    "additions": 10,
                    "deletions": 0,
                },
                {
                    "filename": "tests/test_migration.py",
                    "additions": 15,
                    "deletions": 0,
                },
            ],
        )
    )

    assert result["rollback_plan_exists"] == "Yes"
    assert result["rollback_plan_tested"] == "Yes"


def test_analysis_metadata_is_included():
    result = analyze_change(make_change())

    assert result["analysis"]["files_changed"] == 1
    assert result["analysis"]["author"] == "dev"
    assert result["system"] == "acme/payments"
