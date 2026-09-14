import { useEffect, useState } from "react";
import { api } from "../api";
import Badge from "../components/Badge";
import AssessmentDetailModal from "../components/AssessmentDetailModal";
import { Search, Download, Filter, History as HistoryIcon, ArrowUpRight, Calendar, Server, Tag, Shield } from "lucide-react";

export default function History() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("All");
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedItem, setSelectedItem] = useState(null);

  useEffect(() => {
    api.history().then(setRows).catch((err) => console.error(err)).finally(() => setLoading(false));
  }, []);

  const filtered = rows.filter((r) => {
    const matchesFilter = filter === "All" || r.risk_level === filter;
    const matchesSearch =
      r.system.toLowerCase().includes(searchTerm.toLowerCase()) ||
      r.change_type.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (r.requester_team && r.requester_team.toLowerCase().includes(searchTerm.toLowerCase()));
    return matchesFilter && matchesSearch;
  });

  const exportCSV = () => {
    if (filtered.length === 0) return;
    const headers = ["ID", "Date", "System", "Change Type", "Size", "Team", "Risk Level", "Recommendation", "Justification"];
    const csvRows = [headers.join(",")];
    filtered.forEach((r) => {
      const row = [
        r.id,
        `"${r.created_at}"`,
        `"${r.system}"`,
        `"${r.change_type}"`,
        `"${r.change_size || ''}"`,
        `"${r.requester_team || ''}"`,
        `"${r.risk_level}"`,
        `"${r.recommendation}"`,
        `"${(r.justification || '').replace(/"/g, '""')}"`,
      ];
      csvRows.push(row.join(","));
    });

    const blob = new Blob([csvRows.join("\n")], { type: "text/csv" });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `changeguard_assessments_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
  };

  return (
    <div className="animate-in space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-1.5 text-xs font-bold text-indigo-600 uppercase tracking-wider mb-1">
            <HistoryIcon className="w-4 h-4" /> Assessment Repository
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900">Historical Records</h1>
          <p className="text-slate-500 text-sm mt-0.5">Audit log of all evaluated IT changes across production systems.</p>
        </div>

        <button
          onClick={exportCSV}
          disabled={filtered.length === 0}
          className="self-start sm:self-auto flex items-center gap-2 bg-white hover:bg-slate-50 disabled:opacity-50 text-slate-700 font-semibold text-xs px-4 py-2.5 rounded-xl border border-slate-200 shadow-xs transition-colors cursor-pointer"
        >
          <Download className="w-4 h-4 text-indigo-600" />
          Export CSV ({filtered.length})
        </button>
      </div>

      {/* Filter and Search Bar */}
      <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs p-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
        {/* Search */}
        <div className="relative flex-1 max-w-md">
          <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search by system name, change type, or team..."
            className="w-full pl-10 pr-4 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:bg-white transition-all text-slate-800"
          />
        </div>

        {/* Risk Tabs */}
        <div className="flex items-center gap-1 bg-slate-100/80 p-1 rounded-xl border border-slate-200/60">
          {["All", "High", "Medium", "Low"].map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                filter === f
                  ? "bg-white text-slate-900 shadow-xs ring-1 ring-slate-200/80"
                  : "text-slate-500 hover:text-slate-800"
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {/* Table Container */}
      <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs overflow-hidden">
        {loading ? (
          <div className="p-12 text-center text-sm text-slate-400 animate-pulse">Loading assessment records...</div>
        ) : filtered.length === 0 ? (
          <div className="p-16 text-center">
            <p className="text-sm font-semibold text-slate-600">No matching assessment records found.</p>
            <p className="text-xs text-slate-400 mt-1">Try resetting search filters or launch a new change assessment.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="bg-slate-50/80 border-b border-slate-200 text-slate-400 font-bold uppercase tracking-wider">
                  <th className="px-5 py-3.5">Timestamp</th>
                  <th className="px-5 py-3.5">System</th>
                  <th className="px-5 py-3.5">Change Type</th>
                  <th className="px-5 py-3.5">Risk Rating</th>
                  <th className="px-5 py-3.5">Recommendation</th>
                  <th className="px-5 py-3.5 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filtered.map((r) => (
                  <tr
                    key={r.id}
                    onClick={() => setSelectedItem(r)}
                    className="hover:bg-indigo-50/30 transition-colors cursor-pointer group"
                  >
                    <td className="px-5 py-4 font-mono text-slate-500 whitespace-nowrap">{r.created_at}</td>
                    <td className="px-5 py-4 font-bold text-slate-900 group-hover:text-indigo-600 transition-colors">
                      {r.system}
                    </td>
                    <td className="px-5 py-4 text-slate-600 font-medium">{r.change_type}</td>
                    <td className="px-5 py-4"><Badge value={r.risk_level} /></td>
                    <td className="px-5 py-4"><Badge value={r.recommendation} /></td>
                    <td className="px-5 py-4 text-right">
                      <span className="inline-flex items-center gap-1 font-semibold text-indigo-600 group-hover:underline">
                        Details <ArrowUpRight className="w-3.5 h-3.5" />
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Modal View */}
      {selectedItem && (
        <AssessmentDetailModal item={selectedItem} onClose={() => setSelectedItem(null)} />
      )}
    </div>
  );
}
