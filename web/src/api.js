const BASE = "/api";

async function post(path, body) {
  const res = await fetch(BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Request failed: ${res.status}`);
  return res.json();
}

async function get(path) {
  const res = await fetch(BASE + path);
  if (!res.ok) throw new Error(`Request failed: ${res.status}`);
  return res.json();
}

export const api = {
  assess: (change) => post("/assess", change),
  assessAutonomous: (change) => post("/assess-autonomous", change),
  history: () => get("/history"),
  getAssessment: (id) => get(`/assessments/${id}`),
  stats: () => get("/stats"),
};