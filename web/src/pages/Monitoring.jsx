import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Activity, Gavel, RefreshCcw, ShieldAlert, TrendingUp, Database, AlertTriangle } from "lucide-react";
import { api } from "../api";

// Verdict colours are the app's status colours (same as the badges).
const VERDICTS = [
  { key: "APPROVE", color: "#10b981" },
  { key: "REVIEW", color: "#f59e0b" },
  { key: "REJECT", color: "#f43f5e" },
];

const DRIFT_STYLE = {
  stable: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  moderate: "bg-amber-50 text-amber-800 ring-amber-200",
  significant: "bg-rose-50 text-rose-700 ring-rose-200",
};

const DECISION_STYLE = {
  promoted: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  would_promote: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  kept: "bg-slate-100 text-slate-700 ring-slate-200",
  skipped: "bg-slate-100 text-slate-500 ring-slate-200",
};

const pct = (v) => (v === null || v === undefined ? "–" : `${Math.round(v * 100)}%`);

export default function Monitoring() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.monitoring().then(setData).catch((e) => setError(e?.message || "Failed to load monitoring data"));
  }, []);

  if (error) {
    return (
      <div className="bg-rose-50 border border-rose-200 text-rose-800 p-4 rounded-xl text-sm flex items-center gap-2">
        <AlertTriangle className="w-5 h-5" /> {error}
      </div>
    );
  }
  if (!data) return <div className="py-16 text-center text-sm text-slate-400 animate-pulse">Loading monitoring…</div>;

  const { volume, cab, outcomes, drift, screening, models, retraining } = data;

  return (
    <div className="animate-in space-y-7">
      <div>
        <h1 className="text-3xl font-extrabold tracking-tight text-slate-900">Model Monitoring</h1>
        <p className="text-sm text-slate-500 mt-1 max-w-3xl">
          Is ChangeGuard still right after deployment? Everything here is computed from the audit trail: how it is
          used, whether the CAB trusts it, how its recommendations turned out, whether today's changes still look
          like the data it learned from, and how it has been retrained.
        </p>
      </div>

      {/* KPI tiles */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Tile icon={Activity} label={`Assessments, last ${volume.last_days} days`} value={volume.in_window}
          text={`${volume.total} in total · ${volume.by_kind.ticket || 0} tickets, ${volume.by_kind.code || 0} code`} />
        <Tile icon={Gavel} label="CAB override rate" value={pct(cab.override_rate)}
          text={cab.firm_recommendations_decided
            ? `${cab.overrides} of ${cab.firm_recommendations_decided} firm AI calls overruled`
            : "No CAB decisions on a firm AI call yet"}
          note={cab.demo_decisions ? `${cab.demo_decisions} of ${cab.decided} decisions are demo-seeded` : null} />
        <Tile icon={RefreshCcw} label="Failure rate after approval" value={
            outcomes.recorded ? `${pct(outcomes.ai_flagged.bad_rate)} vs ${pct(outcomes.ai_approved.bad_rate)}` : "No data"}
          text={outcomes.recorded
            ? "Changes the AI flagged vs changes it approved"
            : "Record real outcomes on approved changes"}
          note={outcomes.demo ? `${outcomes.demo} of ${outcomes.recorded} outcomes are demo-seeded` : null} />
        <Tile icon={ShieldAlert} label="Prompt injections caught" value={screening.flagged}
          text={screening.screened ? `in ${screening.screened} RedTeamGPT-screened assessments` : "Prompt screening has not run yet"}
          note={screening.unavailable ? `${screening.unavailable} ran while RedTeamGPT was unreachable` : null} />
      </div>

      {/* Verdicts per day */}
      <Card title="Recommendations per day" hint={`Last ${volume.last_days} days, by the policy's verdict`}>
        <div className="flex flex-wrap gap-4 mb-3 text-xs">
          {VERDICTS.map((v) => (
            <span key={v.key} className="flex items-center gap-2 text-slate-600">
              <span className="w-2.5 h-2.5 rounded-sm" style={{ background: v.color }} />
              {v.key} <span className="font-mono font-semibold text-slate-800">{volume.by_verdict[v.key]}</span>
            </span>
          ))}
        </div>
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={volume.by_day} barCategoryGap="20%">
              <CartesianGrid vertical={false} stroke="#e2e8f0" />
              <XAxis dataKey="date" tickFormatter={(d) => d.slice(5)} tick={{ fontSize: 11, fill: "#64748b" }}
                tickLine={false} axisLine={{ stroke: "#cbd5e1" }} minTickGap={24} />
              <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "#64748b" }} tickLine={false} axisLine={false} width={28} />
              <Tooltip cursor={{ fill: "#f1f5f9" }}
                contentStyle={{ backgroundColor: "#0f172a", borderRadius: 8, border: "none", color: "#fff", fontSize: 12 }}
                itemStyle={{ color: "#e2e8f0" }} />
              {VERDICTS.map((v, i) => (
                <Bar key={v.key} dataKey={v.key} stackId="v" fill={v.color} stroke="#ffffff" strokeWidth={1}
                  isAnimationActive={false}
                  radius={i === VERDICTS.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* CAB vs AI */}
        <Card title="CAB decision vs AI recommendation" hint="Rows: what ChangeGuard recommended · columns: what the board decided">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-slate-400 uppercase tracking-wider">
                <th className="text-left font-bold py-2">AI said</th>
                <th className="text-right font-bold py-2">CAB approved</th>
                <th className="text-right font-bold py-2">CAB rejected</th>
              </tr>
            </thead>
            <tbody>
              {VERDICTS.map((v) => {
                const row = cab.matrix[v.key];
                const overrideCell = (decision) =>
                  (v.key === "APPROVE" && decision === "REJECT") || (v.key === "REJECT" && decision === "APPROVE");
                return (
                  <tr key={v.key} className="border-t border-slate-100">
                    <td className="py-2 font-semibold text-slate-700">{v.key}</td>
                    {["APPROVE", "REJECT"].map((d) => (
                      <td key={d} className={`py-2 text-right font-mono ${overrideCell(d) && row[d] ? "text-rose-700 font-bold" : "text-slate-700"}`}>
                        {row[d]}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="text-xs text-slate-500 mt-3">
            Red cells are overrides: the board went against a firm APPROVE or REJECT (a written reason is required).
            REVIEW leaves the call to the board. {cab.pending} assessment(s) await a decision.
          </p>
        </Card>

        {/* Outcomes */}
        <Card title="Recommendation vs real outcome" hint="Only CAB-approved changes get an outcome">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-slate-400 uppercase tracking-wider">
                <th className="text-left font-bold py-2">AI said</th>
                <th className="text-right font-bold py-2">Success</th>
                <th className="text-right font-bold py-2">Failed</th>
                <th className="text-right font-bold py-2">Caused incident</th>
              </tr>
            </thead>
            <tbody>
              {VERDICTS.map((v) => {
                const row = outcomes.by_recommendation[v.key] || {};
                return (
                  <tr key={v.key} className="border-t border-slate-100">
                    <td className="py-2 font-semibold text-slate-700">{v.key}</td>
                    <td className="py-2 text-right font-mono text-slate-700">{row.Success || 0}</td>
                    <td className="py-2 text-right font-mono text-slate-700">{row.Failed || 0}</td>
                    <td className="py-2 text-right font-mono text-slate-700">{row["Caused-Incident"] || 0}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="text-xs text-slate-500 mt-3">
            If the model is useful, changes it flagged (REVIEW/REJECT) should fail more often than changes it approved.
            {outcomes.recorded
              ? ` Here: ${pct(outcomes.ai_flagged.bad_rate)} of ${outcomes.ai_flagged.n} flagged vs ${pct(outcomes.ai_approved.bad_rate)} of ${outcomes.ai_approved.n} approved.`
              : ""}
            {outcomes.demo ? ` ${outcomes.demo} outcome(s) are demo-seeded and are never used for retraining.` : ""}
          </p>
        </Card>
      </div>

      {/* Drift */}
      <Card title="Input drift vs the training data"
        hint="Population Stability Index (PSI) per feature: below 0.10 stable · 0.10–0.25 moderate shift · above 0.25 significant shift">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {[["ticket", "Change-ticket model", "Rabobank BPIC 2014 training rows"],
            ["code", "Code-change model", "ApacheJIT training rows"]].map(([kind, title, source]) => (
            <DriftPanel key={kind} title={title} source={source} report={drift[kind]} />
          ))}
        </div>
        <p className="text-xs text-slate-500 mt-4">
          A significant shift means today's changes do not look like the history the model learned from, so its
          scores deserve less trust. The fix is to retrain on the organisation's own change history.
        </p>
      </Card>

      {/* Retraining */}
      <Card title="Learning loop: gated retraining"
        hint="Recorded real outcomes become training data; a candidate replaces the model only if it is not worse on the held-out test set">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
          {Object.entries(models).map(([kind, m]) => (
            <div key={kind} className="p-3 rounded-xl bg-slate-50 border border-slate-200/70 text-xs">
              <div className="font-bold text-slate-800">{m.name}</div>
              <div className="text-slate-500 mt-1">
                Held-out ROC-AUC <span className="font-mono font-semibold text-slate-800">{m.roc_auc}</span> · trained {m.trained_at}
                {m.feedback_rows ? ` · includes ${m.feedback_rows} recorded outcome(s)` : " · no recorded outcomes used yet"}
              </div>
            </div>
          ))}
        </div>

        {retraining.length === 0 ? (
          <p className="text-sm text-slate-500">No retraining runs yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-slate-400 uppercase tracking-wider">
                  <th className="text-left font-bold py-2">When</th>
                  <th className="text-left font-bold py-2">Model</th>
                  <th className="text-right font-bold py-2">New outcomes</th>
                  <th className="text-right font-bold py-2">AUC current → candidate</th>
                  <th className="text-left font-bold py-2 pl-4">Decision</th>
                </tr>
              </thead>
              <tbody>
                {retraining.map((r, i) => (
                  <tr key={i} className="border-t border-slate-100 align-top">
                    <td className="py-2 pr-4 font-mono text-xs text-slate-600 whitespace-nowrap">{r.at}</td>
                    <td className="py-2 text-slate-700">{r.model}</td>
                    <td className="py-2 text-right font-mono text-slate-700">{r.feedback_rows}</td>
                    <td className="py-2 text-right font-mono text-slate-700 whitespace-nowrap">
                      {r.current_roc_auc !== undefined ? `${r.current_roc_auc} → ${r.candidate_roc_auc}` : "–"}
                    </td>
                    <td className="py-2 pl-4">
                      <span className={`inline-block px-2 py-0.5 rounded-md text-xs font-semibold ring-1 ${DECISION_STYLE[r.decision] || DECISION_STYLE.kept}`}>
                        {r.decision.replace("_", " ")}
                      </span>
                      <div className="text-xs text-slate-500 mt-1">{r.reason}</div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="text-xs text-slate-500 mt-4 flex items-center gap-1.5">
          <Database className="w-3.5 h-3.5" />
          Run offline where the training data is: <code className="font-mono text-slate-700">python scripts/retrain_with_feedback.py</code>
        </p>
      </Card>

      <p className="text-[11px] text-slate-400">Generated {data.generated_at}</p>
    </div>
  );
}

function DriftPanel({ title, source, report }) {
  if (!report) return null;

  const header = (
    <div className="flex items-center justify-between mb-2">
      <div>
        <div className="font-bold text-sm text-slate-800">{title}</div>
        <div className="text-[11px] text-slate-400">{report.n} live assessment(s) vs {source}</div>
      </div>
      {DRIFT_STYLE[report.status] && <StatusChip status={report.status} />}
    </div>
  );

  if (report.status === "no_reference") {
    return <div>{header}<p className="text-xs text-slate-500">No reference profile. Run <code className="font-mono">python scripts/build_reference_profile.py</code>.</p></div>;
  }
  if (report.status === "insufficient") {
    return <div>{header}<p className="text-xs text-slate-500">Needs at least {report.min} assessments to measure drift; {report.n} so far.</p></div>;
  }

  return (
    <div>
      {header}
      {report.n < 100 && (
        <p className="text-[11px] text-amber-700 mb-2">Small sample ({report.n}): indicative only.</p>
      )}
      <table className="w-full text-sm">
        <tbody>
          {report.features.map((f) => (
            <tr key={f.feature} className="border-t border-slate-100">
              <td className="py-1.5 text-slate-700">{f.label}</td>
              <td className="py-1.5 text-right font-mono text-slate-700">{f.psi.toFixed(2)}</td>
              <td className="py-1.5 pl-3 text-right"><StatusChip status={f.status} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatusChip({ status }) {
  return (
    <span className={`inline-block px-2 py-0.5 rounded-md text-[11px] font-semibold ring-1 capitalize ${DRIFT_STYLE[status]}`}>
      {status}
    </span>
  );
}

function Card({ title, hint, children }) {
  return (
    <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs p-6">
      <h3 className="font-bold text-base text-slate-900 tracking-tight flex items-center gap-2">
        <TrendingUp className="w-4 h-4 text-indigo-600" /> {title}
      </h3>
      {hint && <p className="text-xs text-slate-500 mt-0.5 mb-4">{hint}</p>}
      {children}
    </div>
  );
}

function Tile({ icon: Icon, label, value, text, note }) {
  return (
    <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs p-5">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">{label}</span>
        <div className="w-8 h-8 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center">
          <Icon className="w-4 h-4" />
        </div>
      </div>
      <div className="text-2xl font-extrabold text-slate-900 tracking-tight">{value}</div>
      <p className="text-xs text-slate-500 mt-1">{text}</p>
      {note && <p className="text-[11px] text-amber-700 mt-1">{note}</p>}
    </div>
  );
}
