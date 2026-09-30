# ChangeGuard pull-request check

Every pull request to this repository is assessed by ChangeGuard:

1. The workflow sends the PR's changed-file list (never the code).
2. ChangeGuard scores it with the code-risk model trained on 106,674 real
   Apache commits, finds the most similar real commits, and applies the
   deterministic risk policy.
3. One comment is posted on the PR and updated on every push.
4. The assessment appears in ChangeGuard's History, awaiting a CAB decision.
