import React, { useState } from "react";
import { ShieldCheck, Cpu, Layers, CheckCircle2, Zap, Server, Activity, ArrowRight, Code2 } from "lucide-react";

export default function About() {
  const [activeTab, setActiveTab] = useState("overview");

  const components = [
    {
      n: "01",
      t: "Machine Learning Risk Classifier",
      badge: "XGBoost / LightGBM",
      d: "Predicts historical failure probability from structured attributes (system, change type, window, rollback state, team). Produces calibrated probability score.",
    },
    {
      n: "02",
      t: "Vector RAG (FAISS Index)",
      badge: "all-MiniLM-L6-v2",
      d: "Performs dense semantic vector similarity search against historical IT changes. Finds nearest neighbor past deployments and retrieves real-world incident outcomes.",
    },
    {
      n: "03",
      t: "Deterministic Evidence Tools",
      badge: "Python Tools",
      d: "Performs real-time zero-hallucination checks against system incident logs, schedule window conflicts, and rollback preparation safety metrics.",
    },
    {
      n: "04",
      t: "LangGraph Autonomous Agent",
      badge: "StateGraph Engine",
      d: "An LLM agent loop that dynamically determines which evidence tools to invoke, analyzes returns, and formulates a reasoned recommendation.",
    },
    {
      n: "05",
      t: "Verification & Anti-Hallucination Safeguards",
      badge: "Evidence Validation",
      d: "Cross-checks every statement in the justification against extracted tool evidence to guarantee zero hallucinated facts in CAB reports.",
    },
  ];

  return (
    <div className="animate-in space-y-8 max-w-5xl">
      {/* Header */}
      <div>
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-50 border border-indigo-200 text-indigo-700 text-xs font-semibold mb-2">
          <Cpu className="w-3.5 h-3.5 text-indigo-600" />
          Technical Architecture & Specification
        </div>
        <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900">ChangeGuard System Design</h1>
        <p className="text-slate-500 text-sm mt-1">Multi-modal AI risk assessment engine for mission-critical enterprise software deployments.</p>
      </div>

      {/* Hero Banner */}
      <div className="bg-gradient-to-br from-slate-900 via-slate-800 to-indigo-950 text-white rounded-3xl p-7 shadow-xl border border-slate-800 space-y-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-indigo-500/20 border border-indigo-400/30 flex items-center justify-center text-indigo-400 font-bold">
            <ShieldCheck className="w-6 h-6" />
          </div>
          <div>
            <h3 className="font-extrabold text-lg text-white">Why ChangeGuard?</h3>
            <p className="text-slate-400 text-xs font-mono">Solving Enterprise Change Advisory Board (CAB) Bottlenecks</p>
          </div>
        </div>
        <p className="text-slate-300 text-sm leading-relaxed">
          Traditional Change Advisory Boards rely on manual spreadsheets, subjective opinion, and gut feeling. Low-risk routine patches take days to get approved while high-risk changes often slip through unnoticed. ChangeGuard automates CAB reviews by combining machine learning risk scoring, vector RAG past change retrieval, and LangGraph multi-agent reasoning.
        </p>
      </div>

      {/* Architectural Flow Diagram */}
      <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs p-6 space-y-6">
        <h3 className="font-bold text-base text-slate-900 tracking-tight flex items-center gap-2">
          <Activity className="w-5 h-5 text-indigo-600" />
          End-to-End Execution Pipeline
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-5 gap-3 relative">
          <PipelineStep step="1" title="Change Request" desc="Structured JSON Payload & Params" color="border-slate-200 bg-slate-50" />
          <PipelineStep step="2" title="ML Model" desc="Probabilistic Failure Classifier" color="border-indigo-200 bg-indigo-50/50" />
          <PipelineStep step="3" title="FAISS RAG" desc="Dense Vector Match & Similarity" color="border-purple-200 bg-purple-50/50" />
          <PipelineStep step="4" title="LangGraph" desc="Autonomous Multi-Tool Agent" color="border-indigo-200 bg-indigo-50/50" />
          <PipelineStep step="5" title="CAB Verdict" desc="Approve / Review / Reject + Justification" color="border-emerald-200 bg-emerald-50/50" />
        </div>
      </div>

      {/* Component Breakdown List */}
      <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs p-6 space-y-4">
        <h3 className="font-bold text-base text-slate-900 tracking-tight flex items-center gap-2">
          <Layers className="w-5 h-5 text-indigo-600" />
          Core Engine Modules
        </h3>

        <div className="space-y-3">
          {components.map((c) => (
            <div key={c.n} className="p-4 rounded-xl border border-slate-100 hover:border-indigo-200 bg-slate-50/60 transition-colors flex items-start gap-4">
              <span className="font-mono text-xs font-bold text-indigo-600 bg-indigo-100/80 w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0">
                {c.n}
              </span>
              <div className="space-y-1 flex-1">
                <div className="flex items-center justify-between">
                  <h4 className="font-bold text-sm text-slate-900">{c.t}</h4>
                  <span className="text-[10px] font-mono font-bold bg-slate-200/70 text-slate-700 px-2.5 py-0.5 rounded-full">
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

function PipelineStep({ step, title, desc, color }) {
  return (
    <div className={`p-4 rounded-xl border ${color} space-y-1 flex flex-col justify-between text-left`}>
      <span className="text-[10px] font-mono font-bold text-slate-400">STEP {step}</span>
      <h4 className="font-bold text-xs text-slate-900 mt-1">{title}</h4>
      <p className="text-[11px] text-slate-500 leading-tight">{desc}</p>
    </div>
  );
}
