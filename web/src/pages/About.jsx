import React, { useEffect, useState } from "react";
import { ShieldCheck, Cpu, Layers, Activity, BarChart3, AlertTriangle } from "lucide-react";
import { api } from "../api";

const components = [
  {
    n: "01",
    t: "ML Risk Classifier",
    badge: "Logistic Regression (calibrated)",
    d: "Predicts the probability that a change fails or causes an incident from its structured attributes (system, change type, size, window, rollback state, team) plus history features the backend derives itself. Sigmoid-calibrated so the probability is meaningful, with a decision threshold tuned for F1.",
  },
  {
    n: "02",
    t: "Retrieval over Past Changes",
    badge: "FAISS + all-MiniLM-L6-v2",
    d: "Embeds the change request and finds the most similar historical changes (cosine similarity ≥ 0.70) with their real outcomes. The same retrieval also produces the model's similar-change features, identically in training and at runtime.",
  },
  {
    n: "03",
    t: "Deterministic Evidence Tools",
    badge: "Python",
    d: "Rule-based lookups for system incident history, schedule-window risk, and rollback readiness, plus a structural check that an uploaded rollback document contains a real numbered procedure. The document result is stored server-side, so it cannot be faked by the client.",
  },
  {
    n: "04",
    t: "Deterministic Risk Policy",
    badge: "Authoritative",
    d: "Combines the ML probability and evidence signals into a transparent score (REVIEW ≥ 0.30, REJECT ≥ 0.55). This policy — not the LLM — decides APPROVE / REVIEW / REJECT, so every recommendation is reproducible and auditable.",
  },
  {
    n: "05",
    t: "LLM Explanation & LangGraph Agent",
    badge: "Groq · LangGraph",
    d: "The LLM only writes a justification for the decision the policy already made, using the gathered evidence. In autonomous mode (admins) a LangGraph agent chooses which evidence tools to call. If the LLM is unavailable a rule-based explanation is used, and the UI says so.",
  },
  {
    n: "06",
    t: "Human CAB Decision & Feedback Loop",
    badge: "Human-in-the-loop",
    d: "ChangeGuard advises; a reviewer records the final CAB decision (overriding the AI requires a reason). After implementation, the real outcome is recorded, measuring how often changes that went badly had been flagged.",
  },
];

export default function About() {
  const [metrics, setMetrics] = useState(null);
  const [metricsError, setMetricsError] = useState(null);

  useEffect(() => {
    api
      .modelMetrics()
      .then(setMetrics)
      .catch((e) => setMetricsError(e?.message || "Metrics unavailable"));
  }, []);

  return (
    <div className="animate-in space-y-8 max-w-5xl">
      {/* Header */}
      <div>
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-50 border border-indigo-200 text-indigo-700 text-xs font-semibold mb-2">
          <Cpu className="w-3.5 h-3.5 text-indigo-600" />
          Technical Architecture & Specification
        </div>
        <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900">ChangeGuard System Design</h1>
        <p className="text-slate-500 text-sm mt-1">AI-assisted change risk assessment for enterprise Change Advisory Boards.</p>
      </div>

      {/* Hero Banner */}
      <div className="bg-gradient-to-br from-slate-900 via-slate-800 to-indigo-950 text-white rounded-3xl p-7 shadow-xl border border-slate-800 space-y-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-indigo-500/20 border border-indigo-400/30 flex items-center justify-center text-indigo-400 font-bold">
            <ShieldCheck className="w-6 h-6" />
          </div>
          <div>
            <h3 className="font-extrabold text-lg text-white">Why ChangeGuard?</h3>
            <p className="text-slate-400 text-xs font-mono">Solving Change Advisory Board (CAB) bottlenecks</p>
          </div>
        </div>
        <p className="text-slate-300 text-sm leading-relaxed">
          CAB reviews often rely on spreadsheets and gut feeling: routine patches wait days for approval while risky changes slip through. ChangeGuard gives the board a consistent, evidence-grounded first assessment — an ML risk score, similar past changes and their outcomes, and deterministic evidence checks — combined by an auditable policy, explained in plain language, and left to a human to decide.
        </p>
      </div>

      {/* Pipeline */}
      <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs p-6 space-y-6">
        <h3 className="font-bold text-base text-slate-900 tracking-tight flex items-center gap-2">
          <Activity className="w-5 h-5 text-indigo-600" />
          End-to-End Pipeline
        </h3>

        <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
          <PipelineStep step="1" title="Change Request" desc="Form or GitHub commit/PR" color="border-slate-200 bg-slate-50" />
          <PipelineStep step="2" title="FAISS Retrieval" desc="Similar past changes" color="border-purple-200 bg-purple-50/50" />
          <PipelineStep step="3" title="ML Model" desc="Calibrated failure probability" color="border-indigo-200 bg-indigo-50/50" />
          <PipelineStep step="4" title="Risk Policy" desc="Deterministic APPROVE / REVIEW / REJECT" color="border-amber-200 bg-amber-50/50" />
          <PipelineStep step="5" title="LLM Explanation" desc="Evidence-grounded justification" color="border-indigo-200 bg-indigo-50/50" />
          <PipelineStep step="6" title="CAB Decision" desc="Human approves or rejects" color="border-emerald-200 bg-emerald-50/50" />
        </div>
      </div>

      {/* Model card */}
      <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs p-6 space-y-4">
        <h3 className="font-bold text-base text-slate-900 tracking-tight flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-indigo-600" />
          Model Card
        </h3>

        {metricsError && <p className="text-xs text-slate-500">{metricsError}</p>}

        {metrics && (
          <div className="space-y-4">
            <p className="text-xs text-slate-500">
              {metrics.model_type} · <span className="font-mono">{metrics.model_version}</span> · trained {metrics.trained_at} on {metrics.train_rows} rows, evaluated on {metrics.test_rows} held-out rows ({Math.round(metrics.test_bad_rate * 100)}% bad outcomes).
            </p>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Metric label="ROC-AUC" value={metrics.roc_auc} hint="Ranking quality (0.5 = random)" />
              <Metric label="Recall (bad)" value={metrics.recall} hint="Share of bad changes caught" />
              <Metric label="Precision (bad)" value={metrics.precision} hint="Flags that were truly bad" />
              <Metric label="Brier score" value={metrics.brier_score} hint="Probability error (lower is better)" />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <p className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2">Calibration (held-out)</p>
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-slate-400 text-left">
                      <th className="py-1 font-semibold">Mean predicted</th>
                      <th className="py-1 font-semibold">Observed bad rate</th>
                    </tr>
                  </thead>
                  <tbody className="font-mono text-slate-700">
                    {metrics.calibration.map((c, i) => (
                      <tr key={i} className="border-t border-slate-100">
                        <td className="py-1">{Math.round(c.predicted * 100)}%</td>
                        <td className="py-1">{Math.round(c.observed * 100)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div>
                <p className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2">Top feature influence</p>
                <div className="space-y-1">
                  {metrics.feature_influence.slice(0, 6).map((f) => (
                    <div key={f.feature} className="flex justify-between text-xs border-t border-slate-100 py-1">
                      <span className="text-slate-700">{f.feature}</span>
                      <span className={`font-mono ${f.coefficient > 0 ? "text-rose-600" : "text-emerald-600"}`}>
                        {f.coefficient > 0 ? "+" : ""}
                        {f.coefficient}
                      </span>
                    </div>
                  ))}
                </div>
                <p className="text-[10px] text-slate-400 mt-1">Coefficients on label-encoded inputs; direction is indicative only.</p>
              </div>
            </div>

            <div className="p-3 rounded-xl bg-amber-50 border border-amber-200 text-xs text-amber-900 flex gap-2">
              <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <span>
                Limitations: trained on a synthetic ~600-change dataset, so absolute accuracy will differ on real CAB data. Rollback document verification is a structural heuristic, not a semantic review. The recorded outcomes are the path to retraining on real data.
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Components */}
      <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs p-6 space-y-4">
        <h3 className="font-bold text-base text-slate-900 tracking-tight flex items-center gap-2">
          <Layers className="w-5 h-5 text-indigo-600" />
          Core Modules
        </h3>

        <div className="space-y-3">
          {components.map((c) => (
            <div key={c.n} className="p-4 rounded-xl border border-slate-100 hover:border-indigo-200 bg-slate-50/60 transition-colors flex items-start gap-4">
              <span className="font-mono text-xs font-bold text-indigo-600 bg-indigo-100/80 w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0">
                {c.n}
              </span>
              <div className="space-y-1 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <h4 className="font-bold text-sm text-slate-900">{c.t}</h4>
                  <span className="text-[10px] font-mono font-bold bg-slate-200/70 text-slate-700 px-2.5 py-0.5 rounded-full text-right">
                    {c.badge}
                  </span>
                </div>
                <p className="text-xs text-slate-600 leading-relaxed">{c.d}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value, hint }) {
  return (
    <div className="p-3 rounded-xl bg-slate-50 border border-slate-200/60">
      <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">{label}</div>
      <div className="text-xl font-extrabold font-mono text-slate-900">{value}</div>
      <div className="text-[10px] text-slate-500">{hint}</div>
    </div>
  );
}

function PipelineStep({ step, title, desc, color }) {
  return (
    <div className={`p-4 rounded-xl border ${color} space-y-1 flex flex-col justify-between text-left`}>
      <span className="text-[10px] font-mono font-bold text-slate-400">STEP {step}</span>
      <h4 className="font-bold text-xs text-slate-900 mt-1">{title}</h4>
      <p className="text-[11px] text-slate-500 leading-tight">{desc}</p>
    </div>
  );
}
