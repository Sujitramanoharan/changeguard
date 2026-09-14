import React from "react";
import Badge from "./Badge";
import { X, ShieldAlert, CheckCircle2, Clock, Server, AlertTriangle, Layers, Calendar, RotateCcw, Cpu, Copy, FileText, Activity } from "lucide-react";

export default function AssessmentDetailModal({ item, onClose }) {
  if (!item) return null;

  const details = item.details || {};
  const ml = details.ml_prediction || { risk_probability: item.risk_probability || 0, risk_level: item.risk_level };
  const similar = details.similar_changes || [];
  const evidence = details.evidence || {};
  const tools = details.tools_called || [];

  const copySummary = () => {
    const text = `ChangeGuard Risk Assessment
System: ${item.system} (${item.change_type})
Risk Level: ${item.risk_level}
Recommendation: ${item.recommendation}
Justification: ${item.justification}`;
    navigator.clipboard.writeText(text);
    alert("Assessment summary copied to clipboard!");
  };

  const probPercent = Math.round((ml.risk_probability || 0) * 100);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs animate-in">
      <div className="bg-white rounded-2xl shadow-2xl border border-slate-200/80 w-full max-w-3xl max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-900 text-white">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-indigo-600/30 border border-indigo-400/40 flex items-center justify-center text-indigo-400 font-bold">
              <Activity className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400 font-mono">ID #{item.id}</span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 font-medium">{item.created_at}</span>
              </div>
              <h2 className="text-lg font-bold text-white tracking-tight">{item.system} &bull; {item.change_type}</h2>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Scrollable Body */}
        <div className="p-6 overflow-y-auto space-y-6 flex-1 bg-slate-50/50">

          {/* Top Result Card */}
          <div className="bg-white p-5 rounded-xl border border-slate-200/80 shadow-xs flex flex-col md:flex-row gap-6 items-center justify-between">
            <div className="space-y-2">
              <p className="text-xs font-bold text-slate-400 uppercase tracking-wider">Final Decision</p>
              <div className="flex items-center gap-3">
                <Badge value={item.recommendation} />
                <Badge value={item.risk_level} />
              </div>
              <p className="text-xs text-slate-500">
                Mode: <span className="font-semibold text-slate-700 capitalize">{details.mode || "Controlled"} Engine</span>
              </p>
            </div>

            {/* Risk Gauge Bar */}
            <div className="w-full md:w-64 bg-slate-50 p-3.5 rounded-xl border border-slate-200/60">
              <div className="flex justify-between items-center text-xs mb-1.5">
                <span className="font-semibold text-slate-600">ML Risk Probability</span>
                <span className={`font-mono font-bold ${probPercent > 50 ? 'text-red-600' : probPercent > 25 ? 'text-amber-600' : 'text-emerald-600'}`}>
                  {probPercent}%
                </span>
              </div>
              <div className="w-full h-3 bg-slate-200 rounded-full overflow-hidden">
                <div
                  className={`h-full transition-all duration-500 rounded-full ${
                    probPercent > 50 ? 'bg-gradient-to-r from-amber-500 to-red-600' : probPercent > 25 ? 'bg-gradient-to-r from-emerald-500 to-amber-500' : 'bg-emerald-500'
                  }`}
                  style={{ width: `${Math.max(probPercent, 6)}%` }}
                ></div>
              </div>
              <div className="flex justify-between text-[10px] text-slate-400 mt-1">
                <span>0% Safe</span>
                <span>50%</span>
                <span>100% Critical</span>
              </div>
            </div>
          </div>

          {/* Justification Box */}
          <div className="bg-white p-5 rounded-xl border border-slate-200/80 shadow-xs">
            <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
              <FileText className="w-4 h-4 text-indigo-600" />
              AI Risk Justification Narrative
            </h3>
            <p className="text-sm text-slate-700 leading-relaxed font-sans bg-slate-50 p-4 rounded-lg border border-slate-200/60">
              {item.justification}
            </p>
          </div>

          {/* Tools Logged (if autonomous) */}
          {tools.length > 0 && (
            <div className="bg-white p-5 rounded-xl border border-slate-200/80 shadow-xs">
              <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                <Cpu className="w-4 h-4 text-indigo-600" />
                LangGraph Autonomous Tool Execution Trail
              </h3>
              <div className="flex flex-wrap gap-2">
                {tools.map((t, idx) => (
                  <span key={idx} className="text-xs font-mono bg-indigo-50 text-indigo-700 px-3 py-1 rounded-md border border-indigo-200/60 font-semibold flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-indigo-500"></span>
                    {t}()
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Similar Past Changes (RAG) */}
          {similar.length > 0 && (
            <div className="bg-white p-5 rounded-xl border border-slate-200/80 shadow-xs">
              <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-1.5">
                <Layers className="w-4 h-4 text-indigo-600" />
                FAISS Vector RAG: Historical Match Analysis
              </h3>
              <div className="space-y-2">
                {similar.map((s, idx) => (
                  <div key={idx} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg border border-slate-200/50 text-xs">
                    <div>
                      <span className="font-bold text-slate-800">{s.change_id}</span> &bull; <span className="text-slate-600">{s.change_type} on {s.system}</span>
                      <span className="ml-2 font-mono text-[11px] text-indigo-600 bg-indigo-50 px-1.5 py-0.5 rounded font-medium">
                        {(s.similarity * 100).toFixed(0)}% match
                      </span>
                    </div>
                    <Badge value={s.outcome === "Success" ? "Low" : (s.outcome === "Failed" ? "Medium" : "High")} />
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Evidence Details Grid */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-xs">
              <div className="flex items-center gap-2 text-xs font-semibold text-slate-500 mb-1">
                <Server className="w-4 h-4 text-indigo-600" />
                Incident History
              </div>
              <p className="text-xs text-slate-700 mt-1">{evidence.incidents?.note || "Checked system logs."}</p>
            </div>

            <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-xs">
              <div className="flex items-center gap-2 text-xs font-semibold text-slate-500 mb-1">
                <Calendar className="w-4 h-4 text-amber-600" />
                Schedule Window
              </div>
              <p className="text-xs text-slate-700 mt-1">{evidence.schedule?.note || item.requested_window}</p>
            </div>

            <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-xs">
              <div className="flex items-center gap-2 text-xs font-semibold text-slate-500 mb-1">
                <RotateCcw className="w-4 h-4 text-emerald-600" />
                Rollback Preparedness
              </div>
              <p className="text-xs text-slate-700 mt-1">{evidence.rollback?.note || `Plan exists: ${item.rollback_plan_exists}`}</p>
            </div>
          </div>

          {/* Change Payload Spec */}
          <div className="bg-white p-5 rounded-xl border border-slate-200/80 shadow-xs">
            <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Change Request Details</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
              <div><span className="text-slate-400 block">Requester Team:</span> <span className="font-semibold text-slate-700">{item.requester_team}</span></div>
              <div><span className="text-slate-400 block">Change Size:</span> <span className="font-semibold text-slate-700">{item.change_size}</span></div>
              <div><span className="text-slate-400 block">Requested Window:</span> <span className="font-semibold text-slate-700">{item.requested_window}</span></div>
              <div><span className="text-slate-400 block">Rollback Exists:</span> <span className="font-semibold text-slate-700">{item.rollback_plan_exists}</span></div>
            </div>
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
