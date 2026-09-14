import { NavLink, Outlet } from "react-router-dom";
import { LayoutDashboard, PlusCircle, History as HistoryIcon, Info, ShieldCheck, Sparkles, Activity } from "lucide-react";

const links = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/new", label: "New Assessment", icon: PlusCircle, highlight: true },
  { to: "/history", label: "History", icon: HistoryIcon },
  { to: "/about", label: "Architecture", icon: Info },
];

export default function Layout() {
  return (
    <div className="flex min-h-screen bg-slate-50 text-slate-900 font-sans selection:bg-indigo-500 selection:text-white">
      {/* Sidebar */}
      <aside className="w-64 bg-slate-900 text-white flex flex-col p-4 fixed top-0 left-0 bottom-0 z-30 border-r border-slate-800 shadow-xl">
        
        {/* Brand Header */}
        <div className="flex items-center gap-3 px-2 py-3 mb-6 border-b border-slate-800/80">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 via-purple-500 to-pink-500 flex items-center justify-center font-black text-white text-lg shadow-lg shadow-indigo-500/25 ring-1 ring-white/20">
            <ShieldCheck className="w-5 h-5" />
          </div>
          <div>
            <span className="font-extrabold text-lg tracking-tight text-white block leading-none">ChangeGuard</span>
            <span className="text-[10px] font-mono text-indigo-400 uppercase tracking-widest block mt-1 font-semibold">AI Risk Engine</span>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex flex-col gap-1.5 flex-1">
          {links.map((l) => {
            const Icon = l.icon;
            return (
              <NavLink
                key={l.to}
                to={l.to}
                end={l.to === "/"}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-sm font-semibold transition-all duration-200 ${
                    isActive
                      ? "bg-gradient-to-r from-indigo-600 to-indigo-700 text-white shadow-md shadow-indigo-600/30"
                      : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-100"
                  }`
                }
              >
                <Icon className="w-4 h-4 opacity-90 flex-shrink-0" />
                <span className="flex-1">{l.label}</span>
                {l.highlight && (
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                )}
              </NavLink>
            );
          })}
        </nav>

        {/* Live System Status Pill */}
        <div className="mt-auto pt-4 border-t border-slate-800/80">
          <div className="bg-slate-800/60 border border-slate-700/50 rounded-xl p-3 text-xs space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="text-slate-400 font-medium text-[11px]">System Status</span>
              <span className="flex items-center gap-1.5 text-emerald-400 font-semibold text-[11px]">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                Active
              </span>
            </div>
            <div className="text-[10.5px] font-mono text-slate-400 flex justify-between pt-1 border-t border-slate-700/40">
              <span>LangGraph + FAISS</span>
              <span className="text-indigo-400">v1.0.0</span>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 ml-64 min-h-screen px-8 py-8 max-w-[1360px]">
        <Outlet />
      </main>
    </div>
  );
}