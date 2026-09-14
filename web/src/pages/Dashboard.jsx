import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import Badge from "../components/Badge";
import AssessmentDetailModal from "../components/AssessmentDetailModal";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, BarChart, Bar, XAxis, YAxis } from "recharts";
import { ShieldCheck, ShieldAlert, CheckCircle2, AlertOctagon, Plus, ChevronRight, Activity, Cpu, ArrowUpRight } from "lucide-react";

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedItem, setSelectedItem] = useState(null);

  useEffect(() => {
    Promise.all([api.stats(), api.history()])
      .then(([s, h]) => {
        setStats(s);
        setHistory(h);
      })
      .catch((err) => console.error("Failed to load dashboard data", err))
      .finally(() => setLoading(false));
  }, []);

  const total = stats?.total || 0;
  const highRisk = stats?.high_risk || 0;
  const mediumRisk = stats?.medium_risk || 0;
  const lowRisk = stats?.low_risk || 0;
  const rejected = stats?.rejected || 0;
  const approvalRate = total > 0 ? Math.round(((total - rejected) / total) * 100) : 100;

  const pieData = [
    { name: "High Risk", value: highRisk, color: "#e11d48" },
    { name: "Medium Risk", value: mediumRisk, color: "#f59e0b" },
    { name: "Low Risk", value: lowRisk, color: "#10b981" },
  ].filter(d => d.value > 0);

  const defaultPie = pieData.length > 0 ? pieData : [{ name: "No data", value: 1, color: "#e2e8f0" }];

  return (
    <div className="animate-in space-y-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 text-white p-7 rounded-3xl shadow-xl border border-slate-800 relative overflow-hidden">
        <div className="relative z-10 space-y-2">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-500/20 border border-indigo-400/30 text-indigo-300 text-xs font-semibold">
            <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
            Enterprise CAB Automation Engine
          </div>
          <h1 className="text-3xl font-extrabold tracking-tight text-white">Change Risk Operations</h1>
          <p className="text-slate-300 text-sm max-w-xl">
            Real-time automated change advisory analysis powered by XGBoost ML, FAISS Vector RAG, and LangGraph autonomous reasoning.
          </p>
        </div>
        <div className="relative z-10 flex items-center gap-3">
          <Link to="/new">
            <button className="flex items-center gap-2 bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 text-white font-bold text-sm px-6 py-3 rounded-xl shadow-lg shadow-indigo-500/25 transition-all hover:scale-[1.02] active:scale-[0.98]">
              <Plus className="w-4 h-4" />
              New Change Assessment
            </button>
          </Link>
        </div>

        {/* Decorative background glow */}
        <div className="absolute -right-12 -bottom-12 w-64 h-64 bg-indigo-600/10 rounded-full blur-3xl pointer-events-none"></div>
      </div>

      {/* KPI Stat Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Total Assessments"
          value={total}
          icon={Activity}
          gradient="from-indigo-500 to-blue-600"
          subText="Evaluated change requests"
        />
        <StatCard
          label="High Risk Flagged"
          value={highRisk}
          icon={ShieldAlert}
          gradient="from-rose-500 to-red-600"
          subText={`${total > 0 ? Math.round((highRisk / total) * 100) : 0}% of total changes`}
        />
        <StatCard
          label="Auto Rejections"
          value={rejected}
          icon={AlertOctagon}
          gradient="from-amber-500 to-orange-600"
          subText="Safeguarded from production"
        />
        <StatCard
          label="Approval Rate"
          value={`${approvalRate}%`}
          icon={CheckCircle2}
          gradient="from-emerald-500 to-teal-600"
          subText="CAB cleared changes"
        />
      </div>

      {/* Main Grid: Activity Feed & Visual Analytics */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Left 2 Cols: Recent Activity Stream */}
        <div className="lg:col-span-2 bg-white rounded-2xl border border-slate-200/80 shadow-xs p-6 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-5">
              <div>
                <h3 className="font-bold text-base text-slate-900 tracking-tight">Recent Assessments</h3>
                <p className="text-xs text-slate-500 mt-0.5">Click any record to inspect full AI reasoning, tools, and evidence graph.</p>
              </div>
              <Link to="/history" className="text-xs font-semibold text-indigo-600 hover:text-indigo-700 flex items-center gap-1">
                View all history <ChevronRight className="w-3.5 h-3.5" />
              </Link>
            </div>

            {loading ? (
              <div className="py-12 text-center text-sm text-slate-400 animate-pulse">Loading assessments...</div>
            ) : history.length === 0 ? (
              <div className="py-12 text-center bg-slate-50 rounded-xl border border-dashed border-slate-200">
                <p className="text-sm font-medium text-slate-600">No change assessments evaluated yet.</p>
                <p className="text-xs text-slate-400 mt-1">Submit your first change request to see real-time AI risk analysis.</p>
                <Link to="/new" className="inline-block mt-4 text-xs font-bold text-indigo-600 bg-indigo-50 px-4 py-2 rounded-lg border border-indigo-200/60 hover:bg-indigo-100 transition-colors">
                  Create First Assessment &rarr;
                </Link>
              </div>
            ) : (
              <div className="space-y-3">
                {history.slice(0, 5).map((item) => (
                  <div
                    key={item.id}
                    onClick={() => setSelectedItem(item)}
                    className="p-4 rounded-xl border border-slate-100 hover:border-indigo-200 bg-slate-50/50 hover:bg-indigo-50/30 transition-all cursor-pointer flex items-center justify-between group"
                  >
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-sm text-slate-900 group-hover:text-indigo-600 transition-colors">{item.system}</span>
                        <span className="text-slate-400 text-xs">&bull;</span>
                        <span className="text-xs font-medium text-slate-600">{item.change_type}</span>
                      </div>
                      <p className="text-xs text-slate-500 line-clamp-1 max-w-md">{item.justification}</p>
                    </div>

                    <div className="flex items-center gap-3">
                      <div className="flex flex-col items-end gap-1">
                        <Badge value={item.risk_level} />
                        <span className="text-[10px] text-slate-400 font-mono">{item.created_at}</span>
                      </div>
                      <ArrowUpRight className="w-4 h-4 text-slate-400 group-hover:text-indigo-600 transition-colors" />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="mt-6 pt-4 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
            <span className="flex items-center gap-1.5">
              <Cpu className="w-4 h-4 text-indigo-600" />
              Showing top 5 recent CAB evaluation logs
            </span>
            <span className="font-mono text-[11px] text-slate-400">Database: changeguard.db</span>
          </div>
        </div>

        {/* Right 1 Col: Risk Breakdown Chart */}
        <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs p-6 flex flex-col">
          <h3 className="font-bold text-base text-slate-900 tracking-tight mb-1">Risk Profile Distribution</h3>
          <p className="text-xs text-slate-500 mb-4">Breakdown of evaluated changes by risk rating</p>

          <div className="h-52 w-full my-auto flex items-center justify-center">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={defaultPie}
                  dataKey="value"
                  innerRadius={50}
                  outerRadius={75}
                  paddingAngle={4}
                  stroke="none"
                >
                  {defaultPie.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ backgroundColor: "#0f172a", borderRadius: "8px", border: "none", color: "#fff", fontSize: "12px" }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>

          <div className="space-y-2 pt-4 border-t border-slate-100">
            <div className="flex items-center justify-between text-xs">
              <span className="flex items-center gap-2"><span className="w-2.5 h-2.5 rounded-full bg-rose-600"></span> High Risk</span>
              <span className="font-mono font-bold text-slate-700">{highRisk} ({total > 0 ? Math.round((highRisk/total)*100) : 0}%)</span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="flex items-center gap-2"><span className="w-2.5 h-2.5 rounded-full bg-amber-500"></span> Medium Risk</span>
              <span className="font-mono font-bold text-slate-700">{mediumRisk} ({total > 0 ? Math.round((mediumRisk/total)*100) : 0}%)</span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="flex items-center gap-2"><span className="w-2.5 h-2.5 rounded-full bg-emerald-500"></span> Low Risk</span>
              <span className="font-mono font-bold text-slate-700">{lowRisk} ({total > 0 ? Math.round((lowRisk/total)*100) : 0}%)</span>
            </div>
          </div>
        </div>

      </div>

      {/* Modal for full detail view */}
      {selectedItem && (
        <AssessmentDetailModal item={selectedItem} onClose={() => setSelectedItem(null)} />
      )}
    </div>
  );
}

function StatCard({ label, value, icon: Icon, gradient, subText }) {
  return (
    <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs p-5 hover:shadow-md transition-shadow relative overflow-hidden">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">{label}</span>
        <div className={`w-9 h-9 rounded-xl bg-gradient-to-br ${gradient} flex items-center justify-center text-white shadow-xs`}>
          <Icon className="w-4 h-4" />
        </div>
      </div>
      <div className="text-3xl font-extrabold text-slate-900 tracking-tight">{value}</div>
      <p className="text-xs text-slate-500 mt-1 font-medium">{subText}</p>
    </div>
  );
}

function Sparkles({ className }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z" />
    </svg>
  );
}
