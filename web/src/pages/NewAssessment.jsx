import { useState } from "react";
import { api } from "../api";
import Badge from "../components/Badge";
import AssessmentDetailModal from "../components/AssessmentDetailModal";
import {
  Cpu,
  Sparkles,
  AlertTriangle,
  Play,
  CheckCircle2,
  Zap,
  Upload,
  FileText,
  XCircle,
} from "lucide-react";

const SYSTEMS = [
  "Payments-Service",
  "Auth-Service",
  "Billing-DB",
  "Inventory-API",
  "Website-Frontend",
  "Search-Service",
  "Notification-Service",
  "Reporting-DB",
];

const CHANGE_TYPES = [
  "Config-Update",
  "Deployment",
  "Patch",
  "Security-Patch",
  "Infrastructure-Change",
  "Database-Schema-Change",
];

const SIZES = ["Small", "Medium", "Large"];

const TEAMS = [
  "DevOps",
  "Platform",
  "Security",
  "Data-Engineering",
  "Backend",
  "SRE",
];

const WINDOWS = [
  "Off-Hours-Weekday",
  "Weekend",
  "Business-Hours-Weekday",
  "Peak-Hours",
];

const PRESETS = {
  highRisk: {
    system: "Payments-Service",
    change_type: "Database-Schema-Change",
    change_size: "Large",
    requester_team: "Backend",
    requested_window: "Peak-Hours",
    rollback_plan_exists: "No",
    rollback_plan_tested: "None",
    schedule_conflict: "Yes",
    system_incidents_last_90_days: 3,
    similar_past_changes_count: 5,
    similar_past_changes_failure_rate: 0.4,
    description:
      "Adding new indexed transactions column to main payments DB during peak processing hours without tested rollback script.",
  },

  mediumRisk: {
    system: "Auth-Service",
    change_type: "Infrastructure-Change",
    change_size: "Medium",
    requester_team: "Platform",
    requested_window: "Weekend",
    rollback_plan_exists: "Yes",
    rollback_plan_tested: "No",
    schedule_conflict: "No",
    system_incidents_last_90_days: 1,
    similar_past_changes_count: 5,
    similar_past_changes_failure_rate: 0.2,
    description:
      "Upgrading Kubernetes cluster node pool for Auth-Service over the weekend window.",
  },

  lowRisk: {
    system: "Website-Frontend",
    change_type: "Security-Patch",
    change_size: "Small",
    requester_team: "DevOps",
    requested_window: "Off-Hours-Weekday",
    rollback_plan_exists: "Yes",
    rollback_plan_tested: "Yes",
    schedule_conflict: "No",
    system_incidents_last_90_days: 0,
    similar_past_changes_count: 5,
    similar_past_changes_failure_rate: 0.05,
    description:
      "Routine patch update for static asset bundler during off-hours with tested automated rollback.",
  },
};

const DEFAULTS = PRESETS.lowRisk;

export default function NewAssessment() {
  const user = api.getStoredUser();
  const isAdmin = user?.role === "admin";

  const [mode, setMode] = useState("controlled");
  const [form, setForm] = useState(DEFAULTS);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [agentSteps, setAgentSteps] = useState([]);
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [fullModalItem, setFullModalItem] = useState(null);

  const [docName, setDocName] = useState(null);
  const [docChecking, setDocChecking] = useState(false);
  const [docResult, setDocResult] = useState(null);
  const [docError, setDocError] = useState(null);

  function update(key, value) {
    setForm((f) => ({
      ...f,
      [key]: value,
    }));
  }

  function applyPreset(presetKey) {
    setForm(PRESETS[presetKey]);
    setResult(null);
    setError(null);
    setDocName(null);
    setDocResult(null);
    setDocError(null);
  }

  async function handleDocumentUpload(e) {
    const file = e.target.files?.[0];

    if (!file) {
      return;
    }

    setDocName(file.name);
    setDocChecking(true);
    setDocResult(null);
    setDocError(null);

    try {
      const verification = await api.verifyRollbackDocument(file);

      setDocResult(verification);

      setForm((f) => ({
        ...f,
        rollback_document_provided: true,
        rollback_document_verified: verification.verified,
      }));
    } catch (err) {
      setDocError(err?.message || "Could not verify this document.");

      setForm((f) => ({
        ...f,
        rollback_document_provided: true,
        rollback_document_verified: false,
      }));
    } finally {
      setDocChecking(false);
    }
  }

  function clearDocument() {
    setDocName(null);
    setDocResult(null);
    setDocError(null);

    setForm((f) => ({
      ...f,
      rollback_document_provided: false,
      rollback_document_verified: false,
    }));
  }

  function handleModeChange(nextMode) {
    if (nextMode === "autonomous" && !isAdmin) {
      setMode("controlled");
      return;
    }

    setMode(nextMode);
    setResult(null);
    setError(null);
  }

  async function submit() {
    setLoading(true);
    setResult(null);
    setError(null);

    /*
     * Backend authorization is authoritative.
     * The frontend role check prevents reviewers from being offered
     * the autonomous mode, while the API still enforces admin access.
     */
    if (mode === "autonomous" && !isAdmin) {
      setError(
        "Autonomous Agent access is restricted to administrators."
      );
      setLoading(false);
      return;
    }

    const steps =
      mode === "controlled"
        ? [
            "1. Feature Extraction & Encoding",
            "2. ML Risk Model Probability Scoring",
            "3. FAISS Vector RAG Retrieval",
            "4. System Incident & Window Evidence Check",
            "5. LangChain LLM Risk Reasoning & Safeguards",
          ]
        : [
            "1. LangGraph Agent Initializing State",
            "2. Dynamically Selecting Evidence Tools",
            "3. Executing Tool Loop (ML + FAISS + Tools)",
            "4. Verifying Risk Justification & Constraints",
          ];

    setAgentSteps(steps);
    setCurrentStepIndex(0);

    // Simulate animated step progression for visual feedback.
    const interval = setInterval(() => {
      setCurrentStepIndex((prev) => {
        if (prev < steps.length - 1) {
          return prev + 1;
        }

        clearInterval(interval);
        return prev;
      });
    }, 400);

    try {
      let data;

      if (mode === "controlled") {
        data = await api.assess(form);

        setResult({
          ...data,
          mode: "controlled",
        });
      } else {
        data = await api.assessAutonomous(form);

        setResult({
          ...data,
          mode: "autonomous",
        });
      }
    } catch (e) {
      if (e?.message === "Authentication required") {
        return;
      }

      if (e?.message === "Administrator access required") {
        setError(
          "Autonomous Agent access is restricted to administrators."
        );
        return;
      }

      setError(
        e?.message ||
          "Could not reach the ChangeGuard engine backend. Ensure the server is running on port 7860."
      );
    } finally {
      clearInterval(interval);
      setLoading(false);
    }
  }

  const probPercent = result?.ml_prediction
    ? Math.round(result.ml_prediction.risk_probability * 100)
    : 0;

  return (
    <div className="animate-in space-y-8 max-w-6xl">
      {/* Header */}
      <div>
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-50 border border-indigo-200 text-indigo-700 text-xs font-semibold mb-2">
          <Sparkles className="w-3.5 h-3.5 text-indigo-600" />
          Interactive Assessment Studio
        </div>

        <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900">
          Evaluate Change Risk
        </h1>

        <p className="text-slate-500 text-sm mt-1">
          Submit a proposed change request for evidence-grounded risk
          classification.
        </p>
      </div>

      {/* Preset Buttons */}
      <div className="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-xs flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div className="text-xs font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
          <Zap className="w-4 h-4 text-amber-500" />
          Quick Scenario Presets:
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => applyPreset("highRisk")}
            className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-200 transition-colors flex items-center gap-1.5"
          >
            <span className="w-2 h-2 rounded-full bg-rose-600 animate-pulse"></span>
            High Risk DB Migration
          </button>

          <button
            onClick={() => applyPreset("mediumRisk")}
            className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-amber-50 hover:bg-amber-100 text-amber-700 border border-amber-200 transition-colors flex items-center gap-1.5"
          >
            <span className="w-2 h-2 rounded-full bg-amber-500"></span>
            Infra Upgrade (Weekend)
          </button>

          <button
            onClick={() => applyPreset("lowRisk")}
            className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-emerald-50 hover:bg-emerald-100 text-emerald-700 border border-emerald-200 transition-colors flex items-center gap-1.5"
          >
            <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
            Routine Security Patch
          </button>
        </div>
      </div>

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
        {/* Form Column */}
        <div className="lg:col-span-2 bg-white rounded-2xl border border-slate-200/80 shadow-xs p-6 space-y-6">
          {/* Agent Mode Toggle */}
          <div>
            <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">
              Select Reasoning Mode
            </label>

            <div
              className={`grid ${
                isAdmin ? "grid-cols-2" : "grid-cols-1"
              } gap-3 p-1.5 bg-slate-100/80 rounded-xl border border-slate-200/60`}
            >
              {/* Controlled */}
              <button
                type="button"
                onClick={() => handleModeChange("controlled")}
                className={`px-4 py-3 rounded-lg text-xs font-bold transition-all text-left flex flex-col gap-0.5 ${
                  mode === "controlled"
                    ? "bg-white text-indigo-900 shadow-md ring-1 ring-slate-200"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                <span className="flex items-center justify-between">
                  Controlled Pipeline

                  {mode === "controlled" && (
                    <CheckCircle2 className="w-4 h-4 text-indigo-600" />
                  )}
                </span>

                <span className="text-[11px] font-normal text-slate-500">
                  Fixed sequence: ML &rarr; RAG &rarr; Tools &rarr; LLM
                </span>
              </button>

              {/* Autonomous - Admin Only */}
              {isAdmin && (
                <button
                  type="button"
                  onClick={() => handleModeChange("autonomous")}
                  className={`px-4 py-3 rounded-lg text-xs font-bold transition-all text-left flex flex-col gap-0.5 ${
                    mode === "autonomous"
                      ? "bg-white text-indigo-900 shadow-md ring-1 ring-slate-200"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  <span className="flex items-center justify-between">
                    Autonomous Agent

                    <span className="text-[9px] bg-gradient-to-r from-indigo-600 to-purple-600 text-white px-2 py-0.5 rounded-full font-extrabold">
                      LANGGRAPH
                    </span>
                  </span>

                  <span className="text-[11px] font-normal text-slate-500">
                    LLM loop dynamically selects tool invocations
                  </span>
                </button>
              )}
            </div>

            {!isAdmin && (
              <p className="mt-2 text-[11px] text-slate-400">
                Autonomous Agent mode is available to administrators only.
              </p>
            )}
          </div>

          {/* Form Fields */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field label="Target System">
              <Select
                value={form.system}
                onChange={(v) => update("system", v)}
                options={SYSTEMS}
              />
            </Field>

            <Field label="Change Type">
              <Select
                value={form.change_type}
                onChange={(v) => update("change_type", v)}
                options={CHANGE_TYPES}
              />
            </Field>

            <Field label="Scope & Size">
              <Select
                value={form.change_size}
                onChange={(v) => update("change_size", v)}
                options={SIZES}
              />
            </Field>

            <Field label="Requester Team">
              <Select
                value={form.requester_team}
                onChange={(v) => update("requester_team", v)}
                options={TEAMS}
              />
            </Field>

            <Field label="Deployment Window">
              <Select
                value={form.requested_window}
                onChange={(v) => update("requested_window", v)}
                options={WINDOWS}
              />
            </Field>

            <Field label="Rollback Plan Exists">
              <Select
                value={form.rollback_plan_exists}
                onChange={(v) => update("rollback_plan_exists", v)}
                options={["Yes", "No"]}
              />
            </Field>

            <Field label="Rollback Plan Tested">
              <Select
                value={form.rollback_plan_tested}
                onChange={(v) => update("rollback_plan_tested", v)}
                options={["Yes", "No", "None"]}
              />
            </Field>

            <Field label="Schedule Conflict Flag">
              <Select
                value={form.schedule_conflict}
                onChange={(v) => update("schedule_conflict", v)}
                options={["No", "Yes"]}
              />
            </Field>
          </div>

          {/* Rollback Document Upload */}
          <Field label="Rollback Plan Document (optional)">
            <p className="text-xs text-slate-500 mb-2 -mt-0.5">
              Upload the actual rollback runbook. It's checked for a
              real, numbered procedure — a claimed rollback plan that
              isn't backed by a real document raises the risk score.
            </p>

            {!docName ? (
              <label className="flex items-center justify-center gap-2 w-full px-4 py-3 border-2 border-dashed border-slate-300 rounded-xl text-sm text-slate-500 hover:border-indigo-400 hover:text-indigo-600 hover:bg-indigo-50/40 transition-colors cursor-pointer">
                <Upload className="w-4 h-4" />
                Choose a .txt, .md, or .pdf file
                <input
                  type="file"
                  accept=".txt,.md,.pdf"
                  className="hidden"
                  onChange={handleDocumentUpload}
                />
              </label>
            ) : (
              <div
                className={`flex items-center justify-between gap-3 px-4 py-3 rounded-xl border text-sm ${
                  docChecking
                    ? "bg-slate-50 border-slate-200 text-slate-500"
                    : docResult?.verified
                    ? "bg-emerald-50 border-emerald-200 text-emerald-800"
                    : "bg-rose-50 border-rose-200 text-rose-800"
                }`}
              >
                <div className="flex items-center gap-2 min-w-0">
                  <FileText className="w-4 h-4 flex-shrink-0" />
                  <span className="truncate font-medium">{docName}</span>
                </div>

                <div className="flex items-center gap-3 flex-shrink-0">
                  {docChecking && (
                    <span className="text-xs">Verifying…</span>
                  )}

                  {!docChecking && docResult && (
                    <span className="text-xs font-semibold flex items-center gap-1">
                      {docResult.verified ? (
                        <>
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          Verified
                        </>
                      ) : (
                        <>
                          <XCircle className="w-3.5 h-3.5" />
                          Not substantiated
                        </>
                      )}
                    </span>
                  )}

                  {!docChecking && docError && (
                    <span className="text-xs font-semibold">
                      {docError}
                    </span>
                  )}

                  <button
                    type="button"
                    onClick={clearDocument}
                    className="text-xs underline text-slate-400 hover:text-slate-700"
                  >
                    Remove
                  </button>
                </div>
              </div>
            )}

            {!docChecking && docResult && docResult.reasons?.length > 0 && (
              <ul className="mt-2 text-xs text-slate-500 list-disc list-inside space-y-0.5">
                {docResult.reasons.map((r, idx) => (
                  <li key={idx}>{r}</li>
                ))}
              </ul>
            )}
          </Field>

          {/* Description */}
          <Field label="Change Description & Technical Scope">
            <textarea
              rows={3}
              value={form.description}
              onChange={(e) => update("description", e.target.value)}
              placeholder="Describe technical changes, schema modifications, affected dependencies..."
              className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:bg-white transition-all text-slate-800"
            />
          </Field>

          {/* Submit */}
          <button
            onClick={submit}
            disabled={loading}
            className="w-full bg-gradient-to-r from-indigo-600 via-indigo-700 to-purple-700 hover:from-indigo-700 hover:to-purple-800 disabled:opacity-50 text-white font-bold text-sm py-3.5 rounded-xl shadow-lg shadow-indigo-600/25 transition-all flex items-center justify-center gap-2 cursor-pointer"
          >
            {loading ? (
              <>
                <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full spinner"></span>
                Evaluating Change Risk...
              </>
            ) : (
              <>
                <Play className="w-4 h-4 fill-white" />
                Run{" "}
                {mode === "autonomous"
                  ? "LangGraph Autonomous Agent"
                  : "Risk Pipeline Assessment"}
              </>
            )}
          </button>
        </div>

        {/* Live Execution Panel */}
        <div className="bg-slate-900 text-white rounded-2xl p-6 shadow-xl border border-slate-800 space-y-6 sticky top-6">
          <div>
            <div className="flex items-center gap-2 text-indigo-400 text-xs font-mono font-bold uppercase tracking-wider mb-1">
              <Cpu className="w-4 h-4" />
              Live Reasoning Engine
            </div>

            <h3 className="font-extrabold text-lg text-white">
              Execution Monitor
            </h3>
          </div>

          {!loading && !result && (
            <div className="py-12 text-center text-xs text-slate-400 space-y-3">
              <div className="w-12 h-12 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center mx-auto text-indigo-400">
                <Play className="w-5 h-5" />
              </div>

              <p>
                Click{" "}
                <b className="text-slate-200">
                  Run Risk Pipeline Assessment
                </b>{" "}
                to launch AI evaluation.
              </p>
            </div>
          )}

          {loading && (
            <div className="space-y-3">
              <p className="text-xs text-indigo-300 font-semibold flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-indigo-400 animate-ping"></span>
                Processing change parameters...
              </p>

              <div className="space-y-2">
                {agentSteps.map((step, idx) => (
                  <div
                    key={idx}
                    className={`p-3 rounded-xl border text-xs transition-all flex items-center gap-2.5 ${
                      idx === currentStepIndex
                        ? "bg-indigo-950/80 border-indigo-500/80 text-white font-semibold shadow-md shadow-indigo-500/10"
                        : idx < currentStepIndex
                        ? "bg-slate-800/40 border-slate-700/60 text-slate-400"
                        : "bg-slate-950/40 border-slate-800/40 text-slate-600"
                    }`}
                  >
                    {idx <= currentStepIndex ? (
                      <CheckCircle2
                        className={`w-4 h-4 flex-shrink-0 ${
                          idx === currentStepIndex
                            ? "text-indigo-400 animate-pulse"
                            : "text-emerald-400"
                        }`}
                      />
                    ) : (
                      <span className="w-4 h-4 rounded-full border border-slate-700 flex-shrink-0"></span>
                    )}

                    <span>{step}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {result && !loading && (
            <div className="space-y-4">
              <div className="p-4 rounded-xl bg-slate-800/80 border border-slate-700/80 space-y-3">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-400">Status:</span>

                  <span className="text-emerald-400 font-bold flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    Completed
                  </span>
                </div>

                <div className="flex items-center justify-between text-xs border-t border-slate-700/60 pt-2">
                  <span className="text-slate-400">Mode:</span>

                  <span className="text-indigo-300 font-mono capitalize">
                    {result.mode}
                  </span>
                </div>

                {result.tools_called && (
                  <div className="border-t border-slate-700/60 pt-2">
                    <p className="text-[11px] font-bold text-slate-400 uppercase mb-1.5">
                      Tools Executed:
                    </p>

                    <div className="flex flex-wrap gap-1.5">
                      {result.tools_called.map((t, idx) => (
                        <span
                          key={idx}
                          className="font-mono text-[10px] bg-indigo-500/20 text-indigo-300 px-2 py-0.5 rounded border border-indigo-400/30"
                        >
                          {t}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              <button
                onClick={() =>
                  setFullModalItem({
                    ...result,
                    ...form,
                    id: result.id || "NEW",
                  })
                }
                className="w-full bg-slate-800 hover:bg-slate-700 text-white font-semibold text-xs py-2.5 rounded-xl border border-slate-700 transition-colors flex items-center justify-center gap-1.5"
              >
                Inspect Full Assessment JSON & Graph &rarr;
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 p-4 rounded-xl text-sm flex items-center gap-2">
          <AlertTriangle className="w-5 h-5 text-rose-600 flex-shrink-0" />
          {error}
        </div>
      )}

      {/* Result Section */}
      {result && (
        <div className="bg-white rounded-2xl border border-slate-200/80 shadow-lg p-7 space-y-6 animate-in">
          {/* Header Bar */}
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-5 border-b border-slate-100">
            <div>
              <span className="text-xs font-bold text-slate-400 uppercase tracking-wider block mb-1">
                Assessment Outcome
              </span>

              <div className="flex items-center gap-3">
                <Badge value={result.recommendation} />
                <Badge value={result.risk_level} />
              </div>
            </div>

            {/* Gauge */}
            {result.ml_prediction && (
              <div className="bg-slate-50 px-4 py-2.5 rounded-xl border border-slate-200/60 flex items-center gap-4">
                <div>
                  <p className="text-[11px] font-semibold text-slate-400 uppercase">
                    ML Failure Probability
                  </p>

                  <p
                    className={`text-xl font-extrabold font-mono ${
                      probPercent > 50
                        ? "text-red-600"
                        : probPercent > 25
                        ? "text-amber-600"
                        : "text-emerald-600"
                    }`}
                  >
                    {probPercent}%
                  </p>
                </div>

                <div className="w-24 h-2.5 bg-slate-200 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full ${
                      probPercent > 50
                        ? "bg-red-600"
                        : probPercent > 25
                        ? "bg-amber-500"
                        : "bg-emerald-500"
                    }`}
                    style={{
                      width: `${Math.max(probPercent, 5)}%`,
                    }}
                  ></div>
                </div>
              </div>
            )}
          </div>

          {/* Justification */}
          <div>
            <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">
              AI Risk Justification Narrative
            </h4>

            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/70 text-slate-800 text-sm leading-relaxed font-sans">
              {result.justification}
            </div>
          </div>

          {/* RAG Matches */}
          {result.similar_changes &&
            result.similar_changes.length > 0 && (
              <div>
                <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">
                  FAISS RAG Similar Historical Changes
                </h4>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {result.similar_changes.map((s, idx) => (
                    <div
                      key={idx}
                      className="p-3.5 bg-slate-50 rounded-xl border border-slate-200/60 flex items-center justify-between text-xs"
                    >
                      <div>
                        <span className="font-bold text-slate-900">
                          {s.change_id}
                        </span>{" "}
                        &bull;{" "}
                        <span className="text-slate-600">
                          {s.change_type}
                        </span>

                        <span className="ml-2 font-mono text-[10px] bg-indigo-50 text-indigo-700 px-1.5 py-0.5 rounded font-semibold">
                          {(s.similarity * 100).toFixed(0)}% match
                        </span>
                      </div>

                      <Badge value={s.outcome} />
                    </div>
                  ))}
                </div>
              </div>
            )}

          {/* Evidence Details */}
          {result.evidence && (
            <div>
              <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">
                Gathered Tool Evidence Summary
              </h4>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
                {[
                  result.evidence.incidents?.note,
                  result.evidence.schedule?.note,
                  result.evidence.rollback?.note,
                  result.evidence.document?.note,
                ]
                  .filter(Boolean)
                  .map((note, idx) => (
                    <div
                      key={idx}
                      className="p-3.5 bg-slate-50 rounded-xl border border-slate-200/60 text-xs text-slate-700"
                    >
                      {note}
                    </div>
                  ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Full Assessment Detail Modal */}
      {fullModalItem && (
        <AssessmentDetailModal
          item={fullModalItem}
          onClose={() => setFullModalItem(null)}
        />
      )}
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div>
      <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-1.5">
        {label}
      </label>
      {children}
    </div>
  );
}

function Select({ value, onChange, options }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:bg-white transition-all text-slate-800 cursor-pointer"
    >
      {options.map((o) => (
        <option key={o} value={o}>
          {o}
        </option>
      ))}
    </select>
  );
}
