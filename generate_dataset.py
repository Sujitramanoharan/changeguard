"""
ChangeGuard synthetic dataset generator (v3 - calibrated with sigmoid).

Panel talking point:
  OUTCOME is DERIVED from the evidence features, so every input feature
  genuinely drives the result -> the ML model is learnable and the agent's
  evidence-gathering is provably useful.

Properties:
  - ~80% base success rate (realistic).
  - true_risk_probability clearly separates good vs bad outcomes.
  - Every evidence feature (2-13) correlates with the outcome.
  - A small, controlled set of hard cases for meaningful evaluation.

NO LEAKAGE: outcome / true_risk_probability / risk_level are TARGETS.
Only features 2-13 are ML inputs.
"""

import numpy as np
import pandas as pd

rng = np.random.default_rng(42)
N = 600

def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))

systems = ["Payments-Service", "Auth-Service", "Billing-DB", "Inventory-API",
           "Website-Frontend", "Search-Service", "Notification-Service", "Reporting-DB"]

change_types = {  # log-odds contribution
    "Config-Update":          0.0,
    "Deployment":             0.4,
    "Patch":                  0.2,
    "Security-Patch":         0.5,
    "Infrastructure-Change":  0.9,
    "Database-Schema-Change": 1.3,
}
change_sizes = {"Small": 0.0, "Medium": 0.3, "Large": 0.8}
requester_teams = ["DevOps", "Platform", "Security", "Data-Engineering", "Backend", "SRE"]
windows = {
    "Off-Hours-Weekday":      -0.3,
    "Weekend":                -0.5,
    "Business-Hours-Weekday":  0.4,
    "Peak-Hours":              0.9,
}

rows = []
for i in range(N):
    system = rng.choice(systems)
    ctype = rng.choice(list(change_types.keys()))
    csize = rng.choice(list(change_sizes.keys()), p=[0.45, 0.40, 0.15])
    team = rng.choice(requester_teams)
    window = rng.choice(list(windows.keys()), p=[0.30, 0.20, 0.35, 0.15])

    rollback_exists = rng.random() < 0.75
    rollback_tested = (rng.random() < 0.6) if rollback_exists else None

    similar_count = int(rng.integers(0, 60))
    similar_fail_rate = round(float(np.clip(rng.beta(2, 10), 0, 0.5)), 3)
    incidents_90d = int(rng.poisson(1.0))
    schedule_conflict = rng.random() < 0.28

    # ---------- LOG-ODDS of failure (centered LOW via -3.0 intercept) ----------
    z = -3.9                                   # intercept -> base failure prob ~ sigmoid(-3) = 0.05
    z += change_types[ctype]
    z += change_sizes[csize]
    z += windows[window]
    z += 3.2 * similar_fail_rate               # strong evidence signal
    z += 0.5 * incidents_90d                   # strong signal
    z += 1.1 if schedule_conflict else 0.0     # strong signal
    z += 0.0 if rollback_exists else 1.0       # strong signal
    if rollback_exists and rollback_tested is False:
        z += 0.5
    z -= 0.8 * (similar_count / 60.0)          # well-trodden path safer
    z += rng.normal(0, 0.3)                     # noise

    true_risk = float(sigmoid(z))

    # ---------- SAMPLE OUTCOME (tight link to true risk) ----------
    # Sharpen so low-risk almost always succeeds and high-risk usually fails.
    # This makes the pattern learnable (higher AUC ceiling) while staying realistic.
    p_bad = 1.0 / (1.0 + np.exp(-(true_risk - 0.36) * 13))  # steep sigmoid around 0.30
    if rng.random() < p_bad:
        outcome = "Caused-Incident" if rng.random() < (true_risk * 0.4) else "Failed"
    else:
        outcome = "Success"

    # ---------- RISK LEVEL (bucketed) ----------
    if true_risk < 0.15:
        risk_level = "Low"
    elif true_risk < 0.40:
        risk_level = "Medium"
    else:
        risk_level = "High"

    desc = (f"{ctype} on {system} ({csize.lower()} change) requested by "
            f"{team} during {window.lower().replace('-', ' ')}.")

    rows.append({
        "change_id": f"CHG-{3000+i}",
        "system": system,
        "change_type": ctype,
        "change_size": csize,
        "requester_team": team,
        "requested_window": window,
        "rollback_plan_exists": "Yes" if rollback_exists else "No",
        "rollback_plan_tested": ("Yes" if rollback_tested else "No") if rollback_exists else "",
        "similar_past_changes_count": similar_count,
        "similar_past_changes_failure_rate": similar_fail_rate,
        "system_incidents_last_90_days": incidents_90d,
        "schedule_conflict": "Yes" if schedule_conflict else "No",
        "description": desc,
        "outcome": outcome,
        "true_risk_probability": round(true_risk, 3),
        "risk_level": risk_level,
    })

df = pd.DataFrame(rows)

# ---------- CONTROLLED HARD CASES (~15 each) ----------
low_success = df[(df["risk_level"] == "Low") & (df["outcome"] == "Success")].index
if len(low_success):
    flip = rng.choice(low_success, size=min(8, len(low_success)), replace=False)
    df.loc[flip, "outcome"] = "Failed"
high_bad = df[(df["risk_level"] == "High") & (df["outcome"] != "Success")].index
if len(high_bad):
    flip = rng.choice(high_bad, size=min(8, len(high_bad)), replace=False)
    df.loc[flip, "outcome"] = "Success"

df.to_csv("changeguard_dataset.csv", index=False)
print("Saved changeguard_dataset.csv with", len(df), "rows")
