import { useEffect, useState } from "react";
import { api } from "../api";
import Badge from "../components/Badge";
import AssessmentDetailModal from "../components/AssessmentDetailModal";
import {
  RiskGauge,
  FactorBars,
  SimilarList,
  EvidenceGrid,
  SectionTitle,
  screeningLabel,
} from "../components/RiskInsights";
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
  GitPullRequest,
  Search,
  ClipboardList,
  BarChart3,
  Layers,
  FileSearch,
} from "lucide-react";

/** Next date (as a datetime-local string) falling on weekday (Mon=0) and hour. */
function nextSlot(weekday, hour) {
  const d = new Date();
  d.setHours(hour, 0, 0, 0);
  const jsWeekday = (weekday + 1) % 7; // Monday=0 here, Monday=1 in JS
  let add = (jsWeekday - d.getDay() + 7) % 7;
  if (add === 0) add = 7;
  d.setDate(d.getDate() + add);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(hour)}:00`;
}

const PRESETS = {
  high: {
    label: "Online banking release (Sat night)",
    tone: "rose",
    ticket: {
      title: "Online banking web release 24.3",
      ci_type: "application",
      ci_subtype: "Web Based Application",
      change_family: "Release Type",
      risk_classification: "Major Business Change",
      origin: "Incident",
      incidents_30d: 18,
      planned_start: nextSlot(5, 20),
      planned_hours: 6,
      systems_affected: 6,
      downtime: true,
      emergency: false,
      cab_required: true,
      rollback_plan_exists: "Yes",
      rollback_plan_tested: "No",
      schedule_conflict: "No",
      description: "Quarterly release of the customer online-banking portal.",
    },
  },
  medium: {
    label: "Core DB tuning (late evening)",
    tone: "amber",
    ticket: {
      title: "Core DB instance parameter tuning",
      ci_type: "database",
      ci_subtype: "Instance",
      change_family: "Standard Change Type",
      risk_classification: "Business Change",
      origin: "Problem",
      incidents_30d: 3,
      planned_start: nextSlot(3, 22),
      planned_hours: 3,
      systems_affected: 1,
      downtime: true,
      emergency: false,
      cab_required: false,
      rollback_plan_exists: "Yes",
      rollback_plan_tested: "No",
      schedule_conflict: "No",
      description: "Increase buffer cache on the core accounts database instance.",
    },
  },
  low: {
    label: "Windows server patching",
    tone: "emerald",
    ticket: {
      title: "Patch Windows servers - monthly security update",
      ci_type: "computer",
      ci_subtype: "Windows Server",
      change_family: "Standard Change Type",
      risk_classification: "Minor Change",
      origin: "Problem",
      incidents_30d: 0,
      planned_start: nextSlot(1, 10),
      planned_hours: 2,
      systems_affected: 4,
      downtime: false,
      emergency: false,
      cab_required: false,
      rollback_plan_exists: "Yes",
      rollback_plan_tested: "Yes",
      schedule_conflict: "No",
      description: "Monthly OS security patches on the internal file-server cluster.",
    },
  },
};

const TICKET_STEPS = [
  "Rabobank-trained risk model (LightGBM)",
  "Explain the score (SHAP factors)",
  "FAISS search: similar real changes",
  "Incident, start-time & rollback evidence",
  "Deterministic risk policy decides",
  "LLM explains the decision",
];

const AGENT_STEPS = [
  "Deterministic risk policy decides",
  "LangGraph agent starts",
  "Agent selects evidence tools",
  "Agent writes evidence-cited justification",
];

const CODE_STEPS = [
  "Fetch the real diff from GitHub",
  "Compute change metrics (ApacheJIT definitions)",
  "ApacheJIT-trained risk model (LightGBM)",
  "FAISS search: similar real commits",
  "Rollback & test readiness",
  "Policy decides · LLM explains",
];

const TONES = {
  rose: "bg-rose-50 hover:bg-rose-100 text-rose-700 border-rose-200",
  amber: "bg-amber-50 hover:bg-amber-100 text-amber-700 border-amber-200",
  emerald: "bg-emerald-50 hover:bg-emerald-100 text-emerald-700 border-emerald-200",
};

const INPUT =
  "w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:bg-white transition-all text-slate-800";

const EMPTY_DOC = { name: null, checking: false, result: null, error: null, id: null };

export default function NewAssessment() {
  const user = api.getStoredUser();
  const isAdmin = user?.role === "admin";

  const [tab, setTab] = useState("ticket");
  const [mode, setMode] = useState("controlled");
  const [options, setOptions] = useState(null);
  const [ticket, setTicket] = useState(PRESETS.low.ticket);

  const [repoUrl, setRepoUrl] = useState("");
  const [repoAnalyzing, setRepoAnalyzing] = useState(false);
  const [repoPreview, setRepoPreview] = useState(null);
  const [repoError, setRepoError] = useState(null);
  const [codeConflict, setCodeConflict] = useState("No");

  const [doc, setDoc] = useState(EMPTY_DOC);

  const [loading, setLoading] = useState(false);
  const [steps, setSteps] = useState([]);
  const [stepIndex, setStepIndex] = useState(0);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [modalItem, setModalItem] = useState(null);

  useEffect(() => {
    api.formOptions().then(setOptions).catch((e) => setError(e?.message));
  }, []);

  const update = (key, value) => setTicket((t) => ({ ...t, [key]: value }));

  const subtypes = options?.ci_subtype_by_type?.[ticket.ci_type] || [];

  function changeType(ciType) {
    const first = options?.ci_subtype_by_type?.[ciType]?.[0] || "";
    setTicket((t) => ({ ...t, ci_type: ciType, ci_subtype: first }));
  }

  function resetOutputs() {
    setResult(null);
    setError(null);
  }

  function applyPreset(key) {
    setTicket(PRESETS[key].ticket);
    setDoc(EMPTY_DOC);
    resetOutputs();
  }

  function switchTab(next) {
    setTab(next);
    setDoc(EMPTY_DOC);
    resetOutputs();
    if (next === "code") setMode("controlled");
  }

  async function handleDocumentUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;

    setDoc({ ...EMPTY_DOC, name: file.name, checking: true });

    try {
      const verification = await api.verifyRollbackDocument(file);
      setDoc({ ...EMPTY_DOC, name: file.name, result: verification, id: verification.verification_id });
    } catch (err) {
      setDoc({ ...EMPTY_DOC, name: file.name, error: err?.message || "Could not verify this document." });
    }
  }

  async function handleAnalyzeRepo() {
    if (!repoUrl.trim()) return;

    setRepoAnalyzing(true);
    setRepoError(null);
    setRepoPreview(null);
    resetOutputs();

    try {
      setRepoPreview(await api.analyzeRepoChange(repoUrl.trim()));
    } catch (err) {
      setRepoError(err?.message || "Could not analyze this GitHub URL.");
    } finally {
      setRepoAnalyzing(false);
    }
  }

  async function submit() {
    setLoading(true);
    resetOutputs();

    const plan = tab === "code" ? CODE_STEPS : mode === "autonomous" ? AGENT_STEPS : TICKET_STEPS;
    setSteps(plan);
    setStepIndex(0);

    // Visual progress only - the real pipeline runs in one request.
    const interval = setInterval(() => {
      setStepIndex((prev) => (prev < plan.length - 1 ? prev + 1 : prev));
    }, 450);

    try {
      let data;

      if (tab === "code") {
        data = await api.assessCode({
          url: repoUrl.trim(),
          schedule_conflict: codeConflict,
          rollback_document_id: doc.id,
        });
      } else {
        const payload = {
          ...ticket,
          incidents_30d: Number(ticket.incidents_30d),
          planned_hours: Number(ticket.planned_hours),
          systems_affected: Number(ticket.systems_affected),
          rollback_document_id: doc.id,
        };
        data = mode === "autonomous" ? await api.assessAutonomous(payload) : await api.assess(payload);
      }

      setResult(data);
    } catch (e) {
      if (e?.message === "Authentication required") return;

      setError(
        e?.message === "Administrator access required"
          ? "Autonomous Agent access is restricted to administrators."
          : e?.message || "Could not reach the ChangeGuard backend."
      );
    } finally {
      clearInterval(interval);
      setLoading(false);
    }
  }

  const canRun = tab === "ticket" ? Boolean(options) : Boolean(repoUrl.trim());

  return (
    <div className="animate-in space-y-6 max-w-6xl">
      {/* Header */}
      <div>
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-50 border border-indigo-200 text-indigo-700 text-xs font-semibold mb-2">
          <Sparkles className="w-3.5 h-3.5 text-indigo-600" />
          Trained on real change history
        </div>
        <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900">Evaluate Change Risk</h1>
        <p className="text-slate-500 text-sm mt-1">
          Change tickets are scored by a model trained on 26,000 real Rabobank ITIL changes; code changes by a
          model trained on 106,000 real Apache commits.
        </p>
      </div>

      {/* Tabs */}
      <div className="grid grid-cols-2 gap-2 p-1.5 bg-slate-100/80 rounded-2xl border border-slate-200/60 max-w-xl">
        {[
          { key: "ticket", icon: ClipboardList, title: "Change ticket", sub: "ITIL / CAB request" },
          { key: "code", icon: GitPullRequest, title: "Code change", sub: "GitHub commit or PR" },
        ].map(({ key, icon: Icon, title, sub }) => (
          <button
            key={key}
            type="button"
            onClick={() => switchTab(key)}
            className={`px-4 py-2.5 rounded-xl text-left flex items-center gap-3 transition-all ${
              tab === key ? "bg-white shadow-md ring-1 ring-slate-200 text-indigo-900" : "text-slate-500 hover:text-slate-800"
            }`}
          >
            <Icon className={`w-5 h-5 ${tab === key ? "text-indigo-600" : ""}`} />
            <span>
              <span className="block text-sm font-bold">{title}</span>
              <span className="block text-[11px] font-normal text-slate-500">{sub}</span>
            </span>
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
        {/* Form column */}
        <div className="lg:col-span-2 bg-white rounded-2xl border border-slate-200/80 shadow-xs p-6 space-y-6">
          {tab === "ticket" ? (
            <>
              {/* Presets */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="text-xs font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
                  <Zap className="w-4 h-4 text-amber-500" />
                  Example tickets
                </div>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(PRESETS).map(([key, p]) => (
                    <button
                      key={key}
                      type="button"
                      onClick={() => applyPreset(key)}
                      className={`text-xs font-semibold px-3 py-1.5 rounded-lg border transition-colors ${TONES[p.tone]}`}
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Mode - autonomous agent is admin-only */}
              {isAdmin && (
                <div className="grid grid-cols-2 gap-3 p-1.5 bg-slate-100/80 rounded-xl border border-slate-200/60">
                  {[
                    { key: "controlled", title: "Controlled pipeline", sub: "Model → evidence → policy → LLM" },
                    { key: "autonomous", title: "Autonomous agent", sub: "LangGraph picks its own tools" },
                  ].map(({ key, title, sub }) => (
                    <button
                      key={key}
                      type="button"
                      onClick={() => setMode(key)}
                      className={`px-4 py-2.5 rounded-lg text-xs font-bold text-left ${
                        mode === key ? "bg-white text-indigo-900 shadow-md ring-1 ring-slate-200" : "text-slate-600"
                      }`}
                    >
                      <span className="flex items-center justify-between">
                        {title}
                        {mode === key && <CheckCircle2 className="w-4 h-4 text-indigo-600" />}
                      </span>
                      <span className="block text-[11px] font-normal text-slate-500">{sub}</span>
                    </button>
                  ))}
                </div>
              )}

              {!options ? (
                <p className="text-sm text-slate-400 animate-pulse">Loading real system types…</p>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <Field label="Change title" wide>
                    <input className={INPUT} value={ticket.title} onChange={(e) => update("title", e.target.value)} />
                  </Field>

                  <Field label="System type">
                    <Select value={ticket.ci_type} onChange={changeType} options={options.ci_type} />
                  </Field>
                  <Field label="System subtype">
                    <Select value={ticket.ci_subtype} onChange={(v) => update("ci_subtype", v)} options={subtypes} />
                  </Field>

                  <Field label="Change type">
                    <Select value={ticket.change_family} onChange={(v) => update("change_family", v)} options={options.change_family} />
                  </Field>
                  <Field label="Risk classification">
                    <Select value={ticket.risk_classification} onChange={(v) => update("risk_classification", v)} options={options.risk_classification} />
                  </Field>

                  <Field label="Planned start">
                    <input type="datetime-local" className={INPUT} value={ticket.planned_start} onChange={(e) => update("planned_start", e.target.value)} />
                  </Field>
                  <Field label="Planned duration (hours)">
                    <input type="number" min="0.25" step="0.25" className={INPUT} value={ticket.planned_hours} onChange={(e) => update("planned_hours", e.target.value)} />
                  </Field>

                  <Field label="Incidents on this system (last 30 days)">
                    <input type="number" min="0" className={INPUT} value={ticket.incidents_30d} onChange={(e) => update("incidents_30d", e.target.value)} />
                  </Field>
                  <Field label="Systems affected">
                    <input type="number" min="1" className={INPUT} value={ticket.systems_affected} onChange={(e) => update("systems_affected", e.target.value)} />
                  </Field>

                  <Field label="Raised from">
                    <Select value={ticket.origin} onChange={(v) => update("origin", v)} options={options.origin} />
                  </Field>
                  <Field label="Schedule conflict reported">
                    <Select value={ticket.schedule_conflict} onChange={(v) => update("schedule_conflict", v)} options={["No", "Yes"]} />
                  </Field>

                  <Field label="Rollback plan exists">
                    <Select value={ticket.rollback_plan_exists} onChange={(v) => update("rollback_plan_exists", v)} options={["Yes", "No"]} />
                  </Field>
                  <Field label="Rollback plan tested">
                    <Select value={ticket.rollback_plan_tested} onChange={(v) => update("rollback_plan_tested", v)} options={["Yes", "No", "None"]} />
                  </Field>

                  <div className="sm:col-span-2 flex flex-wrap gap-5">
                    <Toggle label="Scheduled downtime" checked={ticket.downtime} onChange={(v) => update("downtime", v)} />
                    <Toggle label="Emergency change" checked={ticket.emergency} onChange={(v) => update("emergency", v)} />
                    <Toggle label="CAB approval required" checked={ticket.cab_required} onChange={(v) => update("cab_required", v)} />
                  </div>

                  <Field label="Description" wide>
                    <textarea rows={2} className={INPUT} value={ticket.description} onChange={(e) => update("description", e.target.value)} />
                  </Field>
                </div>
              )}
            </>
          ) : (
            <>
              <div className="space-y-2">
                <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider">
                  Public GitHub commit or pull request
                </label>
                <div className="flex flex-col sm:flex-row gap-2">
                  <input
                    className={`${INPUT} flex-1`}
                    value={repoUrl}
                    onChange={(e) => {
                      setRepoUrl(e.target.value);
                      setRepoPreview(null);
                    }}
                    placeholder="https://github.com/owner/repo/commit/… or /pull/123"
                  />
                  <button
                    type="button"
                    onClick={handleAnalyzeRepo}
                    disabled={repoAnalyzing || !repoUrl.trim()}
                    className="px-4 py-2.5 rounded-xl text-sm font-semibold bg-slate-900 hover:bg-slate-800 disabled:opacity-50 text-white flex items-center justify-center gap-2"
                  >
                    {repoAnalyzing ? (
                      <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full spinner" />
                    ) : (
                      <Search className="w-3.5 h-3.5" />
                    )}
                    Preview diff
                  </button>
                </div>
                {repoError && <p className="text-xs text-rose-600 font-medium">{repoError}</p>}
              </div>

              {repoPreview && (
                <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl space-y-3">
                  <div className="text-xs text-slate-600">
                    <span className="font-bold text-slate-900">{repoPreview.system}</span> · by{" "}
                    {repoPreview.analysis.author} · {repoPreview.analysis.commit_message.split("\n")[0]}
                  </div>
                  <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
                    {[
                      ["Lines added", repoPreview.code_metrics.la],
                      ["Lines deleted", repoPreview.code_metrics.ld],
                      ["Files", repoPreview.code_metrics.nf],
                      ["Directories", repoPreview.code_metrics.nd],
                      ["Modules", repoPreview.code_metrics.ns],
                      ["Spread", repoPreview.code_metrics.ent.toFixed(2)],
                    ].map(([label, value]) => (
                      <div key={label} className="bg-white rounded-lg border border-slate-200 p-2 text-center">
                        <div className="text-base font-extrabold font-mono text-slate-900">{value}</div>
                        <div className="text-[10px] text-slate-500">{label}</div>
                      </div>
                    ))}
                  </div>
                  <p className="text-[11px] text-slate-500">
                    Detected: {repoPreview.change_type} · rollback / reverse-migration wording{" "}
                    {repoPreview.analysis.detected_rollback_language ? "found" : "not found"} · test files{" "}
                    {repoPreview.analysis.touches_tests ? "changed" : "not changed"}
                  </p>
                </div>
              )}

              <Field label="Deployment window conflicts with another change?">
                <Select value={codeConflict} onChange={setCodeConflict} options={["No", "Yes"]} />
              </Field>
            </>
          )}

          {/* Rollback document (both tabs) */}
          <Field label="Rollback plan document (optional)">
            <p className="text-xs text-slate-500 mb-2 -mt-0.5">
              Checked on the server for a real, numbered procedure. A claimed rollback plan that isn't backed by a
              real document raises the risk score.
            </p>

            {!doc.name ? (
              <label className="flex items-center justify-center gap-2 w-full px-4 py-3 border-2 border-dashed border-slate-300 rounded-xl text-sm text-slate-500 hover:border-indigo-400 hover:text-indigo-600 hover:bg-indigo-50/40 transition-colors cursor-pointer">
                <Upload className="w-4 h-4" />
                Choose a .txt, .md, or .pdf file
                <input type="file" accept=".txt,.md,.pdf" className="hidden" onChange={handleDocumentUpload} />
              </label>
            ) : (
              <div
                className={`flex items-center justify-between gap-3 px-4 py-3 rounded-xl border text-sm ${
                  doc.checking
                    ? "bg-slate-50 border-slate-200 text-slate-500"
                    : doc.result?.verified
                    ? "bg-emerald-50 border-emerald-200 text-emerald-800"
                    : "bg-rose-50 border-rose-200 text-rose-800"
                }`}
              >
                <div className="flex items-center gap-2 min-w-0">
                  <FileText className="w-4 h-4 flex-shrink-0" />
                  <span className="truncate font-medium">{doc.name}</span>
                </div>
                <div className="flex items-center gap-3 flex-shrink-0 text-xs font-semibold">
                  {doc.checking && <span>Verifying…</span>}
                  {!doc.checking && doc.result && (
                    <span className="flex items-center gap-1">
                      {doc.result.verified ? <CheckCircle2 className="w-3.5 h-3.5" /> : <XCircle className="w-3.5 h-3.5" />}
                      {doc.result.verified ? "Verified" : "Not substantiated"}
                    </span>
                  )}
                  {!doc.checking && doc.error && <span>{doc.error}</span>}
                  <button type="button" onClick={() => setDoc(EMPTY_DOC)} className="underline text-slate-400 hover:text-slate-700 font-normal">
                    Remove
                  </button>
                </div>
              </div>
            )}

            {!doc.checking && doc.result?.reasons?.length > 0 && (
              <ul className="mt-2 text-xs text-slate-500 list-disc list-inside space-y-0.5">
                {doc.result.reasons.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            )}
          </Field>

          <button
            onClick={submit}
            disabled={loading || !canRun}
            className="w-full bg-gradient-to-r from-indigo-600 via-indigo-700 to-purple-700 hover:from-indigo-700 hover:to-purple-800 disabled:opacity-50 text-white font-bold text-sm py-3.5 rounded-xl shadow-lg shadow-indigo-600/25 transition-all flex items-center justify-center gap-2"
          >
            {loading ? (
              <>
                <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full spinner" />
                Assessing…
              </>
            ) : (
              <>
                <Play className="w-4 h-4 fill-white" />
                {tab === "code" ? "Assess code change" : mode === "autonomous" ? "Run autonomous agent" : "Assess change ticket"}
              </>
            )}
          </button>
        </div>

        {/* Execution monitor */}
        <div className="bg-slate-900 text-white rounded-2xl p-6 shadow-xl border border-slate-800 space-y-5 lg:sticky lg:top-6">
          <div>
            <div className="flex items-center gap-2 text-indigo-400 text-xs font-mono font-bold uppercase tracking-wider mb-1">
              <Cpu className="w-4 h-4" />
              Pipeline
            </div>
            <h3 className="font-extrabold text-lg">Execution Monitor</h3>
          </div>

          {!loading && !result && (
            <p className="py-10 text-center text-xs text-slate-400">
              {tab === "code"
                ? "Paste a GitHub link, preview the diff, then assess it."
                : "Pick an example or fill in the ticket, then assess it."}
            </p>
          )}

          {loading && (
            <div className="space-y-2">
              {steps.map((step, idx) => (
                <div
                  key={step}
                  className={`p-3 rounded-xl border text-xs flex items-center gap-2.5 ${
                    idx === stepIndex
                      ? "bg-indigo-950/80 border-indigo-500/80 font-semibold"
                      : idx < stepIndex
                      ? "bg-slate-800/40 border-slate-700/60 text-slate-400"
                      : "bg-slate-950/40 border-slate-800/40 text-slate-600"
                  }`}
                >
                  {idx <= stepIndex ? (
                    <CheckCircle2 className={`w-4 h-4 ${idx === stepIndex ? "text-indigo-400 animate-pulse" : "text-emerald-400"}`} />
                  ) : (
                    <span className="w-4 h-4 rounded-full border border-slate-700" />
                  )}
                  {step}
                </div>
              ))}
              <p className="text-[10px] text-slate-500 pt-1">Illustrative progress - the pipeline runs as one request.</p>
            </div>
          )}

          {result && !loading && (
            <div className="space-y-3 text-xs">
              {[
                ["Status", "Completed"],
                ["Model", result.kind === "code" ? "ApacheJIT code model" : "Rabobank change model"],
                ["Mode", result.mode],
                ["Explanation", result.explanation_source === "llm" ? "LLM (Groq)" : "Rule-based fallback"],
                ["Prompt screening", screeningLabel(result.prompt_guard)],
                ["CAB decision", "Pending"],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between gap-3 border-b border-slate-800 pb-2">
                  <span className="text-slate-400">{k}</span>
                  <span className={`font-mono ${k === "CAB decision" ? "text-amber-300" : k === "Status" ? "text-emerald-400" : "text-indigo-200"}`}>
                    {v}
                  </span>
                </div>
              ))}

              {result.tools_called?.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {result.tools_called.map((t, i) => (
                    <span key={`${t}-${i}`} className="font-mono text-[10px] bg-indigo-500/20 text-indigo-300 px-2 py-0.5 rounded">
                      {t}
                    </span>
                  ))}
                </div>
              )}

              <button
                onClick={() => api.getAssessment(result.id).then(setModalItem).catch((e) => setError(e?.message))}
                className="w-full bg-slate-800 hover:bg-slate-700 font-semibold py-2.5 rounded-xl border border-slate-700"
              >
                Open full assessment &amp; record CAB decision →
              </button>
            </div>
          )}
        </div>
      </div>

      {error && (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 p-4 rounded-xl text-sm flex items-center gap-2">
          <AlertTriangle className="w-5 h-5 text-rose-600 flex-shrink-0" />
          {error}
        </div>
      )}

      {result && <ResultPanel result={result} />}

      {modalItem && <AssessmentDetailModal item={modalItem} onClose={() => setModalItem(null)} />}
    </div>
  );
}

function ResultPanel({ result }) {
  const ml = result.ml_prediction;

  return (
    <div className="bg-white rounded-2xl border border-slate-200/80 shadow-lg p-7 space-y-7 animate-in">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-5 pb-5 border-b border-slate-100">
        <div className="space-y-2">
          <span className="text-xs font-bold text-slate-400 uppercase tracking-wider block">Recommendation</span>
          <div className="flex items-center gap-3">
            <Badge value={result.recommendation} />
            <Badge value={result.risk_level} />
          </div>
          <p className="text-xs text-slate-500">
            Policy score <span className="font-mono font-semibold text-slate-700">{result.policy.score}</span>{" "}
            (REVIEW ≥ 0.30 · REJECT ≥ 0.55) - decided by the deterministic policy, not the LLM.
          </p>
        </div>
        <RiskGauge ml={ml} />
      </div>

      {result.prompt_guard?.status === "flagged" && (
        <div className="bg-rose-50 border border-rose-300 text-rose-900 p-4 rounded-xl text-sm flex items-start gap-2">
          <AlertTriangle className="w-5 h-5 text-rose-600 flex-shrink-0 mt-0.5" />
          <span>{result.evidence?.security?.note}</span>
        </div>
      )}

      <div>
        <SectionTitle icon={FileSearch}>Justification</SectionTitle>
        <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/70 text-slate-800 text-sm leading-relaxed">
          {result.justification}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-7">
        <div>
          <SectionTitle icon={BarChart3} hint="SHAP contributions from the trained model for this exact change">
            Why this score
          </SectionTitle>
          <FactorBars factors={ml.factors} />
        </div>
        <div>
          <SectionTitle
            icon={Layers}
            hint={result.kind === "code" ? "Nearest of 106,674 real Apache commits" : "Nearest of ~26,000 real Rabobank changes"}
          >
            Similar real changes &amp; what happened
          </SectionTitle>
          <SimilarList similar={result.similar_changes} kind={result.kind} />
        </div>
      </div>

      <div>
        <SectionTitle>Evidence</SectionTitle>
        <EvidenceGrid evidence={result.evidence} />
      </div>
    </div>
  );
}

function Field({ label, children, wide }) {
  return (
    <div className={wide ? "sm:col-span-2" : ""}>
      <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-1.5">{label}</label>
      {children}
    </div>
  );
}

function Select({ value, onChange, options }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} className={`${INPUT} cursor-pointer`}>
      {options.map((o) => (
        <option key={o} value={o}>
          {o}
        </option>
      ))}
    </select>
  );
}

function Toggle({ label, checked, onChange }) {
  return (
    <label className="inline-flex items-center gap-2 text-sm text-slate-700 cursor-pointer select-none">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="w-4 h-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
      />
      {label}
    </label>
  );
}
