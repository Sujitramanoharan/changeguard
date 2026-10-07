import React, { useState } from "react";
import Badge from "./Badge";
import { api } from "../api";
import { RiskGauge, FactorBars, SimilarList, EvidenceGrid, SectionTitle } from "./RiskInsights";
import { screeningLabel } from "../screening";
import { X, Layers, Cpu, Copy, FileText, Gavel, ClipboardCheck, BarChart3, GitCommit, ClipboardList, ExternalLink } from "lucide-react";

export default function AssessmentDetailModal({ item: initialItem, onClose, onUpdated }) {
  const [item, setItem] = useState(initialItem);

  if (!item) return null;

  const handleUpdated = (updated) => {
    setItem(updated);
    onUpdated?.(updated);
  };

  const details = item.details || {};
  const kind = details.kind || item.assessment_type || "ticket";
  const ml = details.ml_prediction;
  const tools = details.tools_called || [];
  const change = details.change || {};

  const copySummary = () => {
    const text = `ChangeGuard Risk Assessment
${kind === "code" ? "Code change" : "Change ticket"}: ${item.system} (${item.change_type})
Risk Level: ${item.risk_level}${ml ? ` (${ml.relative_risk}x a typical change)` : ""}
Recommendation: ${item.recommendation}
Justification: ${item.justification}
CAB Decision: ${item.cab_decision || "Pending"}${item.cab_decided_by ? ` (by ${item.cab_decided_by})` : ""}`;
    navigator.clipboard.writeText(text);
    alert("Assessment summary copied to clipboard!");
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs animate-in">
      <div className="bg-white rounded-2xl shadow-2xl border border-slate-200/80 w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-900 text-white">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-9 h-9 rounded-xl bg-indigo-600/30 border border-indigo-400/40 flex items-center justify-center text-indigo-400">
              {kind === "code" ? <GitCommit className="w-5 h-5" /> : <ClipboardList className="w-5 h-5" />}
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400 font-mono">ID #{item.id}</span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 font-medium">{item.created_at}</span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 font-medium">
                  {kind === "code" ? "Code change" : "Change ticket"}
                </span>
              </div>
              <h2 className="text-lg font-bold text-white tracking-tight truncate">
                {item.system} &bull; {item.change_type}
              </h2>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Scrollable Body */}
        <div className="p-6 overflow-y-auto space-y-6 flex-1 bg-slate-50/50">
          {/* Decision + gauge */}
          <div className="bg-white p-5 rounded-xl border border-slate-200/80 shadow-xs flex flex-col md:flex-row gap-6 items-start md:items-center justify-between">
            <div className="space-y-2">
              <p className="text-xs font-bold text-slate-400 uppercase tracking-wider">AI recommendation</p>
              <div className="flex items-center gap-3">
                <Badge value={item.recommendation} />
                <Badge value={item.risk_level} />
              </div>
              <p className="text-xs text-slate-500">
                Mode:{" "}
                <span className="font-semibold text-slate-700 capitalize">
                  {details.mode === "ci" ? "GitHub PR check" : details.mode || "controlled"}
                </span>
                {details.explanation_source && (
                  <>
                    {" "}&bull; Explanation:{" "}
                    <span className="font-semibold text-slate-700">
                      {details.explanation_source === "llm" ? "LLM (Groq)" : "Rule-based fallback"}
                    </span>
                  </>
                )}
                {details.prompt_guard && (
                  <>
                    {" "}&bull; Prompt screening:{" "}
                    <span className={`font-semibold ${details.prompt_guard.status === "flagged" ? "text-rose-700" : "text-slate-700"}`}>
                      {screeningLabel(details.prompt_guard)}
                    </span>
                  </>
                )}
              </p>
              {details.policy?.score !== undefined && (
                <p className="text-xs text-slate-500">
                  Policy score: <span className="font-mono font-semibold text-slate-700">{details.policy.score}</span>
                  <span className="text-slate-400"> (REVIEW &ge; 0.30, REJECT &ge; 0.55)</span>
                </p>
              )}
            </div>
            <RiskGauge ml={ml} />
          </div>

          {/* Human CAB decision */}
          <CabPanel item={item} onUpdated={handleUpdated} />

          {/* Justification */}
          <div className="bg-white p-5 rounded-xl border border-slate-200/80 shadow-xs">
            <SectionTitle icon={FileText}>Justification</SectionTitle>
            <p className="text-sm text-slate-700 leading-relaxed bg-slate-50 p-4 rounded-lg border border-slate-200/60">
              {item.justification}
            </p>
          </div>

          {/* Tools (autonomous) */}
          {tools.length > 0 && (
            <div className="bg-white p-5 rounded-xl border border-slate-200/80 shadow-xs">
              <SectionTitle icon={Cpu}>Tools the LangGraph agent chose to call</SectionTitle>
              <div className="flex flex-wrap gap-2">
                {tools.map((t, idx) => (
                  <span key={idx} className="text-xs font-mono bg-indigo-50 text-indigo-700 px-3 py-1 rounded-md border border-indigo-200/60 font-semibold">
                    {t}()
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Factors + similar */}
          {ml?.factors && (
            <div className="bg-white p-5 rounded-xl border border-slate-200/80 shadow-xs grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div>
                <SectionTitle icon={BarChart3} hint="SHAP contributions from the trained model">Why this score</SectionTitle>
                <FactorBars factors={ml.factors} />
              </div>
              <div>
                <SectionTitle icon={Layers} hint={kind === "code" ? "Real Apache commits" : "Real Rabobank changes"}>
                  Similar real changes
                </SectionTitle>
                <SimilarList similar={details.similar_changes} kind={kind} />
              </div>
            </div>
          )}

          {/* Evidence */}
          <div>
            <SectionTitle>Evidence</SectionTitle>
            <EvidenceGrid evidence={details.evidence} />
          </div>

          {/* Change details */}
          <div className="bg-white p-5 rounded-xl border border-slate-200/80 shadow-xs">
            <SectionTitle>{kind === "code" ? "Code change details" : "Change ticket details"}</SectionTitle>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
              {(kind === "code"
                ? [
                    ["Repository", change.system],
                    ["Author", details.analysis?.author],
                    ["Size", item.change_size],
                    ["Tests changed", details.analysis?.touches_tests ? "Yes" : "No"],
                  ]
                : [
                    ["System", `${change.ci_subtype || ""} (${change.ci_type || ""})`],
                    ["Planned start", item.requested_window],
                    ["Duration", change.planned_hours ? `${change.planned_hours} h` : ""],
                    ["Recent incidents", change.incidents_30d],
                    ["Systems affected", change.systems_affected],
                    ["Emergency", change.emergency ? "Yes" : "No"],
                    ["Rollback exists", change.rollback_plan_exists],
                    ["Rollback tested", change.rollback_plan_tested],
                  ]
              ).map(([label, value]) => (
                <div key={label}>
                  <span className="text-slate-400 block">{label}</span>
                  <span className="font-semibold text-slate-700">{value ?? "-"}</span>
                </div>
              ))}
            </div>
            {change.url && (
              <a href={change.url} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-indigo-600 hover:underline">
                View on GitHub <ExternalLink className="w-3 h-3" />
              </a>
            )}
          </div>
        </div>

        {/* Footer Actions */}
        <div className="px-6 py-4 border-t border-slate-200 bg-white flex items-center justify-between">
          <button
            onClick={copySummary}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold bg-slate-100 hover:bg-slate-200 text-slate-700 transition-colors"
          >
            <Copy className="w-4 h-4" />
            Copy Assessment Summary
          </button>
          <button
            onClick={onClose}
            className="px-5 py-2 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-700 text-white transition-colors shadow-xs"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}

const OUTCOME_STYLES = {
  Success: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  Failed: "bg-amber-50 text-amber-800 ring-amber-200",
  "Caused-Incident": "bg-rose-50 text-rose-700 ring-rose-200",
};

function OutcomeBadge({ value }) {
  return (
    <span className={`inline-flex px-2.5 py-0.5 rounded-full text-[11px] font-semibold ring-1 ${OUTCOME_STYLES[value] || "bg-slate-100 text-slate-700 ring-slate-200"}`}>
      {value}
    </span>
  );
}

function CabPanel({ item, onUpdated }) {
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  if (typeof item.id !== "number") return null;

  const run = async (fn) => {
    setBusy(true);
    setError(null);
    try {
      onUpdated(await fn());
      setComment("");
    } catch (e) {
      setError(e?.message || "Could not save.");
    } finally {
      setBusy(false);
    }
  };

  const firmAi = item.recommendation === "APPROVE" || item.recommendation === "REJECT";
  const isOverride = (decision) => firmAi && decision !== item.recommendation;

  return (
    <div className="bg-white p-5 rounded-xl border border-slate-200/80 shadow-xs space-y-3">
      <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
        <Gavel className="w-4 h-4 text-indigo-600" />
        Human CAB Decision
      </h3>

      {item.cab_decision ? (
        <div className="text-xs text-slate-700 space-y-1">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge value={item.cab_decision} />
            <span>
              by <b>{item.cab_decided_by}</b> on {item.cab_decided_at}
            </span>
            {isOverride(item.cab_decision) && (
              <span className="px-2 py-0.5 rounded-full bg-purple-50 text-purple-700 ring-1 ring-purple-200 font-semibold">
                Overrode AI recommendation
              </span>
            )}
          </div>
          {item.cab_comment && (
            <p className="bg-slate-50 p-3 rounded-lg border border-slate-200/60 italic">&ldquo;{item.cab_comment}&rdquo;</p>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          <p className="text-xs text-slate-500">
            ChangeGuard advises; the board decides. Overriding a firm AI recommendation requires a reason.
          </p>
          <textarea
            rows={2}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Comment (required when overriding the AI)"
            className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
          <div className="flex gap-2">
            {["APPROVE", "REJECT"].map((d) => (
              <button
                key={d}
                type="button"
                disabled={busy || (isOverride(d) && !comment.trim())}
                onClick={() => run(() => api.recordDecision(item.id, d, comment))}
                title={isOverride(d) && !comment.trim() ? "Add a comment to override the AI" : ""}
                className={`px-4 py-2 rounded-lg text-xs font-bold text-white disabled:opacity-40 transition-colors ${
                  d === "APPROVE" ? "bg-emerald-600 hover:bg-emerald-700" : "bg-rose-600 hover:bg-rose-700"
                }`}
              >
                {d === "APPROVE" ? "Approve change" : "Reject change"}
                {isOverride(d) ? " (override)" : ""}
              </button>
            ))}
          </div>
        </div>
      )}

      {item.cab_decision === "APPROVE" && (
        <div className="pt-3 border-t border-slate-100 text-xs space-y-2">
          <p className="font-semibold text-slate-600 flex items-center gap-1.5">
            <ClipboardCheck className="w-4 h-4 text-emerald-600" />
            Post-implementation outcome
          </p>
          {item.actual_outcome ? (
            <p className="text-slate-700 flex items-center gap-2">
              <OutcomeBadge value={item.actual_outcome} />
              recorded by <b>{item.outcome_recorded_by}</b> on {item.outcome_recorded_at}
            </p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {["Success", "Failed", "Caused-Incident"].map((o) => (
                <button
                  key={o}
                  type="button"
                  disabled={busy}
                  onClick={() => run(() => api.recordOutcome(item.id, o))}
                  className="px-3 py-1.5 rounded-lg border border-slate-200 bg-slate-50 hover:bg-slate-100 font-semibold text-slate-700 disabled:opacity-40"
                >
                  {o}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {error && <p className="text-xs text-rose-600 font-medium">{error}</p>}
    </div>
  );
}
