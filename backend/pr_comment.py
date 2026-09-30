"""Markdown for the ChangeGuard comment posted on a GitHub pull request."""

# Hidden marker: the workflow finds its previous comment by this and
# updates it instead of adding a new comment on every push.
MARKER = "<!-- changeguard-pr-check -->"

ICONS = {"APPROVE": "✅", "REVIEW": "⚠️", "REJECT": "⛔"}

EVIDENCE_TITLES = {
    "diff": "What the diff touches",
    "rollback": "Rollback readiness",
    "similar": "Similar changes",
}


def build_pr_comment(saved: dict, details_url: str) -> str:
    """Render one saved code assessment as a PR comment."""

    ml = saved["ml_prediction"]
    policy = saved["policy"]
    rec = saved["recommendation"]

    lines = [
        MARKER,
        f"## {ICONS.get(rec, '')} ChangeGuard: **{rec}** · {saved['risk_level']} risk",
        "",
        f"**Model risk:** {ml['relative_risk']}× a typical change "
        f"({ml['risk_probability'] * 100:.1f}% predicted chance of introducing a bug; "
        f"model trained on 106,674 real Apache commits)  ",
        f"**Policy score:** {policy['score']} (REVIEW ≥ 0.30 · REJECT ≥ 0.55) — "
        f"decided by a fixed, auditable policy, not the LLM",
        "",
        "### Why this score",
        "| Factor | This PR | Effect |",
        "|---|---|---|",
    ]

    for f in ml.get("factors", []):
        arrow = "⬆️ raises risk" if f["impact"] > 0 else "⬇️ lowers risk"
        lines.append(f"| {f['label']} | {f['value']} | {arrow} |")

    similar = saved.get("similar_changes") or []
    if similar:
        lines += ["", "### Most similar real commits"]
        for s in similar:
            ref = f"[`{s['change_id']}`]({s['url']})" if s.get("url") else f"`{s['change_id']}`"
            lines.append(f"- {ref} {s['system']} · {s['change_type']} → **{s['outcome']}**")

    evidence = saved.get("evidence") or {}
    notes = [
        f"- **{title}:** {evidence[key]['note']}"
        for key, title in EVIDENCE_TITLES.items()
        if evidence.get(key, {}).get("note")
    ]
    if notes:
        lines += ["", "### Evidence", *notes]

    lines += [
        "",
        "### Justification",
        f"> {saved['justification']}",
        "",
        f"**CAB decision:** pending — [open assessment #{saved['id']} in ChangeGuard]({details_url})",
        "",
        "<sub>ChangeGuard advises; a human decides. This comment updates on every push.</sub>",
    ]

    return "\n".join(lines)
