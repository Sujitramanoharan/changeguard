"""Unit tests for the rollback-document verification heuristic."""

from document_verification import verify_rollback_document


GOOD_DOC = """
Rollback Procedure - Payments Schema Migration

1. Stop the write path by disabling the feature flag split_payments_v2.
2. Restore the transactions table from the pre-migration snapshot.
3. Revert the application deployment to the previous tagged release.
4. Verify checkout succeeds against the restored schema.
5. Notify the on-call channel once recovery is confirmed.
"""


def test_credible_rollback_document_is_verified():
    result = verify_rollback_document(GOOD_DOC)

    assert result["verified"] is True
    assert result["has_numbered_steps"] is True
    assert len(result["matched_keywords"]) >= 2


def test_empty_document_is_not_verified():
    result = verify_rollback_document("")

    assert result["verified"] is False
    assert result["reasons"]


def test_short_unrelated_text_is_not_verified():
    result = verify_rollback_document("Looks fine to me, approved.")

    assert result["verified"] is False


def test_keywords_without_steps_are_not_verified():
    text = (
        "We have a rollback and restore plan and a backup in place, "
        "tested and ready, covering recovery and revert scenarios "
        "thoroughly should anything go wrong during this change."
    )

    result = verify_rollback_document(text)

    assert result["has_numbered_steps"] is False
    assert result["verified"] is False
