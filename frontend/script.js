async function submitAssessment() {
  const payload = {
    system: document.getElementById("system").value,
    change_type: document.getElementById("change_type").value,
    change_size: document.getElementById("change_size").value,
    requester_team: document.getElementById("requester_team").value,
    requested_window: document.getElementById("requested_window").value,
    rollback_plan_exists: document.getElementById("rollback_plan_exists").value,
    rollback_plan_tested: document.getElementById("rollback_plan_tested").value,
    schedule_conflict: document.getElementById("schedule_conflict").value,
    description: document.getElementById("description").value,
    similar_past_changes_count: 10,
    similar_past_changes_failure_rate: 0.2,
    system_incidents_last_90_days: 1,
  };

  const box = document.getElementById("result");
  box.classList.remove("hidden");
  box.innerHTML = '<div class="spinner">Analyzing change... gathering evidence and reasoning...</div>';

  try {
    const res = await fetch("/api/assess", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const d = await res.json();

    const similar = d.similar_changes.map(s =>
      `<div class="evidence-item">${s.change_id}: ${s.change_type} on ${s.system}
       (similarity ${s.similarity}) &rarr; <b>${s.outcome}</b></div>`).join("");

    box.innerHTML = `
      <div class="card">
        <h1>Assessment Result</h1>
        <p style="margin:14px 0">
          <span class="badge ${d.recommendation}">${d.recommendation}</span>
          <span class="badge ${d.risk_level}">Risk: ${d.risk_level}</span>
          <span style="color:#6b7280;margin-left:10px">
            ML failure probability: ${(d.ml_prediction.risk_probability*100).toFixed(0)}%</span>
        </p>
        <h3 style="margin:16px 0 6px">Justification</h3>
        <p>${d.justification}</p>
        <h3 style="margin:20px 0 6px">Evidence: Similar Past Changes</h3>
        ${similar}
        <h3 style="margin:20px 0 6px">Other Evidence</h3>
        <div class="evidence-item">${d.evidence.incidents.note}</div>
        <div class="evidence-item">${d.evidence.schedule.note}</div>
        <div class="evidence-item">${d.evidence.rollback.note}</div>
      </div>`;
  } catch (e) {
    box.innerHTML = '<div class="card">Error: could not reach the server.</div>';
  }
}
