import {
  TrendingUp,
  TrendingDown,
  Layers,
  ExternalLink,
  Server,
  Calendar,
  RotateCcw,
  FileText,
  GitCommit,
  ShieldAlert,
} from "lucide-react";

/** How risky this change is compared with a typical historical change. */
export function RiskGauge({ ml }) {
  if (!ml) return null;

  const rel = ml.relative_risk ?? 0;
  const prob = ml.risk_probability ?? 0;
  // risk_index maps relative risk onto 0-1 (0.5 = average change).
  const pct = Math.round((ml.risk_index ?? 0) * 100);
  const color =
    ml.risk_level === "High"
      ? "from-rose-500 to-red-600"
      : ml.risk_level === "Medium"
      ? "from-amber-400 to-orange-500"
      : "from-emerald-400 to-teal-500";

  return (
    <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/70 min-w-[260px]">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">
          Model risk vs. a typical change
        </span>
        <span className="text-2xl font-extrabold font-mono text-slate-900">
          {rel >= 10 ? rel.toFixed(0) : rel >= 1 ? rel.toFixed(1) : rel.toFixed(2)}×
        </span>
      </div>

      <div className="relative w-full h-2.5 bg-slate-200 rounded-full mt-2 overflow-hidden">
        <div
          className={`h-full rounded-full bg-gradient-to-r ${color} transition-all duration-700`}
          style={{ width: `${Math.max(pct, 4)}%` }}
        />
        {/* Marker for "average change" */}
        <div className="absolute top-0 bottom-0 w-0.5 bg-slate-500/60" style={{ left: "50%" }} />
      </div>

      <div className="flex justify-between text-[10px] text-slate-400 mt-1">
        <span>safer</span>
        <span>average</span>
        <span>riskier</span>
      </div>

      <p className="text-[11px] text-slate-500 mt-2">
        {(prob * 100).toFixed(1)}% predicted probability · typical change{" "}
        {((ml.base_rate ?? 0) * 100).toFixed(1)}% ·{" "}
        {ml.model === "code" ? "ApacheJIT code model" : "Rabobank change model"}
      </p>
      <p className="text-[10px] text-slate-400 mt-1">
        The recommendation also weighs rollback readiness, timing and document evidence.
      </p>
    </div>
  );
}

/** SHAP contributions: what pushed this prediction up or down. */
export function FactorBars({ factors }) {
  if (!factors?.length) return null;

  const max = Math.max(...factors.map((f) => Math.abs(f.impact)), 0.01);

  return (
    <div className="space-y-2">
      {factors.map((f) => {
        const up = f.impact > 0;
        const width = `${Math.max((Math.abs(f.impact) / max) * 100, 4)}%`;

        return (
          <div key={f.feature} className="grid grid-cols-12 items-center gap-3 text-xs">
            <div className="col-span-5 min-w-0">
              <div className="font-semibold text-slate-700 truncate">{f.label}</div>
              <div className="text-slate-400 font-mono truncate">{f.value}</div>
            </div>
            <div className="col-span-5 h-2 bg-slate-100 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full ${up ? "bg-rose-500" : "bg-emerald-500"}`}
                style={{ width }}
              />
            </div>
            <div
              className={`col-span-2 flex items-center justify-end gap-1 font-semibold ${
                up ? "text-rose-600" : "text-emerald-600"
              }`}
            >
              {up ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
              {up ? "raises" : "lowers"}
            </div>
          </div>
        );
      })}
    </div>
  );
}

const OUTCOME_STYLE = {
  bad: "bg-rose-50 text-rose-700 ring-rose-200",
  good: "bg-emerald-50 text-emerald-700 ring-emerald-200",
};

/** The most similar real historical changes and what happened after them. */
export function SimilarList({ similar, kind }) {
  if (!similar?.length) return null;

  return (
    <div className="space-y-2">
      {similar.map((s) => (
        <div
          key={s.change_id}
          className="p-3 bg-slate-50 rounded-xl border border-slate-200/60 flex items-center justify-between gap-3 text-xs"
        >
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 font-bold text-slate-800 whitespace-nowrap">
              {kind === "code" ? <GitCommit className="w-3.5 h-3.5 text-slate-400" /> : null}
              {s.url ? (
                <a
                  href={s.url}
                  target="_blank"
                  rel="noreferrer"
                  className="hover:text-indigo-600 inline-flex items-center gap-1"
                >
                  {s.change_id}
                  <ExternalLink className="w-3 h-3" />
                </a>
              ) : (
                s.change_id
              )}
              <span className="font-mono text-[10px] text-indigo-600 bg-indigo-50 px-1.5 py-0.5 rounded">
                {Math.round((s.similarity ?? 0) * 100)}% match
              </span>
            </div>
            <div className="text-slate-500 truncate">
              {s.system} · {s.change_type} · {s.date}
            </div>
          </div>
          <span
            className={`flex-shrink-0 px-2 py-0.5 rounded-full text-[11px] font-semibold ring-1 ${
              s.bad ? OUTCOME_STYLE.bad : OUTCOME_STYLE.good
            }`}
          >
            {s.outcome}
          </span>
        </div>
      ))}
    </div>
  );
}

const EVIDENCE = [
  { key: "incidents", title: "System incident history", icon: Server, tone: "text-indigo-600" },
  { key: "schedule", title: "Start-time risk", icon: Calendar, tone: "text-amber-600" },
  { key: "diff", title: "What the diff touches", icon: GitCommit, tone: "text-indigo-600" },
  { key: "similar", title: "Similar changes", icon: Layers, tone: "text-purple-600" },
  { key: "rollback", title: "Rollback readiness", icon: RotateCcw, tone: "text-emerald-600" },
  { key: "document", title: "Rollback document", icon: FileText, tone: "text-purple-600" },
  { key: "security", title: "Prompt security (RedTeamGPT)", icon: ShieldAlert, tone: "text-rose-600" },
];

/** Deterministic evidence notes gathered by the tools. */
export function EvidenceGrid({ evidence }) {
  if (!evidence) return null;

  const cards = EVIDENCE.filter((e) => evidence[e.key]?.note);

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
      {cards.map(({ key, title, icon: Icon, tone }) => (
        <div
          key={key}
          className={`p-3.5 rounded-xl border shadow-xs ${
            evidence[key].status === "flagged" ? "bg-rose-50 border-rose-300" : "bg-white border-slate-200/80"
          }`}
        >
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-500 mb-1">
            <Icon className={`w-4 h-4 ${tone}`} />
            {title}
          </div>
          <p className="text-xs text-slate-700 leading-relaxed">{evidence[key].note}</p>
        </div>
      ))}
    </div>
  );
}

/** One-line status of the RedTeamGPT prompt screening. */
export function screeningLabel(guard) {
  return {
    clean: "RedTeamGPT: clean",
    flagged: "RedTeamGPT: injection flagged",
    unavailable: "RedTeamGPT unreachable (LLM skipped)",
  }[guard?.status] || "Off";
}

export function SectionTitle({ icon: Icon, children, hint }) {
  return (
    <div className="mb-3">
      <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
        {Icon ? <Icon className="w-4 h-4 text-indigo-600" /> : null}
        {children}
      </h4>
      {hint ? <p className="text-[11px] text-slate-400 mt-0.5">{hint}</p> : null}
    </div>
  );
}
