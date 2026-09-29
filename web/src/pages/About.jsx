import React, { useEffect, useState } from "react";
import { ShieldCheck, Cpu, Layers, Activity, BarChart3, AlertTriangle, Database, ExternalLink } from "lucide-react";
import { api } from "../api";

const components = [
  {
    n: "01",
    t: "Change-ticket risk model",
    badge: "LightGBM · Rabobank ITIL data",
    d: "Trained on ~26,000 real change records from Rabobank Group ICT (BPI Challenge 2014). Predicts whether incidents on the affected system will rise after the change, from system type, change type, risk classification, timing, duration, scope and recent incident history.",
  },
  {
    n: "02",
    t: "Code-change risk model",
    badge: "LightGBM · ApacheJIT",
    d: "Trained on 106,674 real commits from 15 Apache projects, each labelled bug-inducing or clean. The live app computes the same change metrics (lines, files, directories, modules, spread) from the real GitHub diff.",
  },
  {
    n: "03",
    t: "Explanations (SHAP) & similar changes (FAISS)",
    badge: "TreeSHAP · FAISS",
    d: "Every score shows which factors pushed it up or down, and the most similar real historical changes with what actually happened after them.",
  },
  {
    n: "04",
    t: "Evidence tools & document check",
    badge: "Deterministic",
    d: "Historical incident and start-time risk from the real data, rollback readiness, and a server-side check that an uploaded rollback document contains a real numbered procedure.",
  },
  {
    n: "05",
    t: "Deterministic risk policy",
    badge: "Authoritative",
    d: "Combines the model and the evidence into a readable score (REVIEW ≥ 0.30, REJECT ≥ 0.55). The policy - not the LLM - decides, so every recommendation is reproducible and auditable.",
  },
  {
    n: "06",
    t: "LLM explanation & LangGraph agent",
    badge: "Groq · LangGraph",
    d: "The LLM only explains a decision already made. In autonomous mode (admins) a LangGraph agent chooses which evidence tools to call. Without the LLM, a rule-based explanation is used and labelled as such.",
  },
  {
    n: "07",
    t: "Human CAB decision & feedback loop",
    badge: "Human-in-the-loop",
    d: "A reviewer records the final decision (overriding the AI requires a reason), then the real outcome - the data needed to retrain on an organisation's own history.",
  },
];

const DATASETS = [
  {
    name: "BPI Challenge 2014 - Rabobank Group ICT",
    what: "Real ITIL change, incident and interaction records exported from HP Service Manager.",
    url: "https://data.4tu.nl/collections/BPI_Challenge_2014/5065469",
    license: "4TU.ResearchData terms",
  },
  {
    name: "ApacheJIT (Keshavarz & Nagappan, MSR 2022)",
    what: "106,674 commits from 15 Apache projects labelled bug-inducing via SZZ over real Jira bug reports.",
    url: "https://zenodo.org/records/5907002",
    license: "CC-BY-4.0",
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
      <div>
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-50 border border-indigo-200 text-indigo-700 text-xs font-semibold mb-2">
          <Cpu className="w-3.5 h-3.5 text-indigo-600" />
          Technical architecture
        </div>
        <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900">ChangeGuard System Design</h1>
        <p className="text-slate-500 text-sm mt-1">AI-assisted change risk assessment for Change Advisory Boards, trained on real change history.</p>
      </div>

      <div className="bg-gradient-to-br from-slate-900 via-slate-800 to-indigo-950 text-white rounded-3xl p-7 shadow-xl border border-slate-800 space-y-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-indigo-500/20 border border-indigo-400/30 flex items-center justify-center text-indigo-400">
            <ShieldCheck className="w-6 h-6" />
          </div>
          <div>
            <h3 className="font-extrabold text-lg">Why ChangeGuard?</h3>
            <p className="text-slate-400 text-xs font-mono">Failed changes are a leading cause of outages</p>
          </div>
        </div>
        <p className="text-slate-300 text-sm leading-relaxed">
          CAB reviews often rely on gut feeling: routine changes wait days while risky ones slip through. On the
          real Rabobank data, the bank's own manual risk rating ranked risky changes barely better than chance
          (AUC 0.59). ChangeGuard gives every change a consistent, evidence-grounded assessment learned from real
          history, explained factor by factor, decided by an auditable policy - and left to a human to approve.
        </p>
      </div>

      {/* Pipeline */}
      <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs p-6 space-y-6">
        <h3 className="font-bold text-base text-slate-900 flex items-center gap-2">
          <Activity className="w-5 h-5 text-indigo-600" />
          End-to-end pipeline
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
          <PipelineStep step="1" title="Change" desc="ITIL ticket or GitHub commit / PR" color="border-slate-200 bg-slate-50" />
          <PipelineStep step="2" title="Real-data model" desc="Rabobank or ApacheJIT LightGBM" color="border-indigo-200 bg-indigo-50/50" />
          <PipelineStep step="3" title="SHAP + FAISS" desc="Top factors & similar real changes" color="border-purple-200 bg-purple-50/50" />
          <PipelineStep step="4" title="Risk policy" desc="Deterministic APPROVE / REVIEW / REJECT" color="border-amber-200 bg-amber-50/50" />
          <PipelineStep step="5" title="LLM explanation" desc="Evidence-grounded justification" color="border-indigo-200 bg-indigo-50/50" />
          <PipelineStep step="6" title="CAB decision" desc="Human approves, outcome recorded" color="border-emerald-200 bg-emerald-50/50" />
        </div>
      </div>

      {/* Model cards */}
      <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs p-6 space-y-5">
        <h3 className="font-bold text-base text-slate-900 flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-indigo-600" />
          Model cards - evaluated on held-out real data
        </h3>

        {metricsError && <p className="text-xs text-slate-500">{metricsError}</p>}

        {metrics?.models && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            {metrics.models.ticket && <ModelCard m={metrics.models.ticket} flagLabel="Riskiest 10% flagged" flagKey="top10" />}
            {metrics.models.code && <ModelCard m={metrics.models.code} flagLabel="Riskiest 20% flagged" flagKey="top20" />}
          </div>
        )}

        <div className="p-3 rounded-xl bg-amber-50 border border-amber-200 text-xs text-amber-900 flex gap-2">
          <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <div className="space-y-1">
            <p className="font-semibold">Limitations</p>
            <ul className="list-disc list-inside space-y-0.5">
              <li>Rabobank label is inferred (incidents on the same system rose after the change), from one bank in 2013-14; it partly reflects how incident-prone a system is.</li>
              <li>ApacheJIT labels come from the SZZ algorithm; commit size explains much of the signal, and the projects are Java-heavy.</li>
              <li>Recent ApacheJIT commits are under-labelled (bugs not yet found), so the code model over-predicts on the newest commits.</li>
              <li>An organisation should retrain on its own history - the recorded CAB outcomes are that data.</li>
            </ul>
          </div>
        </div>
      </div>

      {/* Datasets */}
      <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs p-6 space-y-4">
        <h3 className="font-bold text-base text-slate-900 flex items-center gap-2">
          <Database className="w-5 h-5 text-indigo-600" />
          Public datasets
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {DATASETS.map((d) => (
            <a key={d.name} href={d.url} target="_blank" rel="noreferrer" className="p-4 rounded-xl border border-slate-200 hover:border-indigo-300 bg-slate-50/60 block">
              <div className="flex items-center justify-between gap-2">
                <span className="font-bold text-sm text-slate-900">{d.name}</span>
                <ExternalLink className="w-3.5 h-3.5 text-slate-400" />
              </div>
              <p className="text-xs text-slate-600 mt-1">{d.what}</p>
              <p className="text-[11px] text-slate-400 mt-1">License: {d.license}</p>
            </a>
          ))}
        </div>
      </div>

      {/* Components */}
      <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs p-6 space-y-4">
        <h3 className="font-bold text-base text-slate-900 flex items-center gap-2">
          <Layers className="w-5 h-5 text-indigo-600" />
          Core modules
        </h3>
        <div className="space-y-3">
          {components.map((c) => (
            <div key={c.n} className="p-4 rounded-xl border border-slate-100 hover:border-indigo-200 bg-slate-50/60 flex items-start gap-4">
              <span className="font-mono text-xs font-bold text-indigo-600 bg-indigo-100/80 w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0">
                {c.n}
              </span>
              <div className="space-y-1 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <h4 className="font-bold text-sm text-slate-900">{c.t}</h4>
                  <span className="text-[10px] font-mono font-bold bg-slate-200/70 text-slate-700 px-2.5 py-0.5 rounded-full text-right">{c.badge}</span>
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

function ModelCard({ m, flagLabel, flagKey }) {
  const baselines = Object.entries(m.baselines || {});

  return (
    <div className="p-5 rounded-2xl border border-slate-200 bg-slate-50/50 space-y-4">
      <div>
        <h4 className="font-bold text-slate-900">{m.name}</h4>
        <p className="text-[11px] text-slate-500 mt-0.5">{m.dataset}</p>
        <p className="text-[11px] text-slate-500">Label: {m.label}</p>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <Metric label="ROC-AUC" value={m.roc_auc} hint={m.test_period} />
        {m.unseen_projects_roc_auc ? (
          <Metric label="Unseen repos" value={m.unseen_projects_roc_auc} hint="AUC" />
        ) : (
          <Metric label="PR-AUC" value={m.pr_auc} hint={`base ${m.test_positive_rate}`} />
        )}
        <Metric label="Recall" value={m[`${flagKey}_recall`]} hint={flagLabel} />
      </div>

      <div className="text-xs space-y-1">
        <p className="font-semibold text-slate-600">Compared with simple baselines (AUC)</p>
        <div className="flex justify-between border-t border-slate-200 pt-1">
          <span className="text-slate-700">ChangeGuard model</span>
          <span className="font-mono font-bold text-indigo-700">{m.roc_auc}</span>
        </div>
        {baselines.map(([name, value]) => (
          <div key={name} className="flex justify-between border-t border-slate-100 pt-1">
            <span className="text-slate-500">{name}</span>
            <span className="font-mono text-slate-600">{value}</span>
          </div>
        ))}
      </div>

      <div className="text-xs space-y-1">
        <p className="font-semibold text-slate-600">Most important features</p>
        {(m.feature_importance || []).slice(0, 4).map((f) => (
          <div key={f.feature} className="flex items-center gap-2">
            <span className="w-40 truncate text-slate-600">{f.feature}</span>
            <div className="flex-1 h-1.5 bg-slate-200 rounded-full overflow-hidden">
              <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${Math.round(f.share * 100)}%` }} />
            </div>
            <span className="font-mono text-slate-500 w-9 text-right">{Math.round(f.share * 100)}%</span>
          </div>
        ))}
      </div>

      <p className="text-[10px] text-slate-400">
        {m.model_type} · {m.split} · {m.train_rows.toLocaleString()} train / {m.test_rows.toLocaleString()} test rows · trained {m.trained_at}
      </p>
    </div>
  );
}

function Metric({ label, value, hint }) {
  return (
    <div className="p-2.5 rounded-xl bg-white border border-slate-200/70">
      <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">{label}</div>
      <div className="text-lg font-extrabold font-mono text-slate-900">{value}</div>
      <div className="text-[10px] text-slate-500 truncate">{hint}</div>
    </div>
  );
}

function PipelineStep({ step, title, desc, color }) {
  return (
    <div className={`p-4 rounded-xl border ${color} space-y-1 text-left`}>
      <span className="text-[10px] font-mono font-bold text-slate-400">STEP {step}</span>
      <h4 className="font-bold text-xs text-slate-900 mt-1">{title}</h4>
      <p className="text-[11px] text-slate-500 leading-tight">{desc}</p>
    </div>
  );
}
