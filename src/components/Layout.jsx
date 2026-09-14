import { NavLink, Outlet } from "react-router-dom";

const links = [
  { to: "/", label: "Dashboard", icon: "M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z" },
  { to: "/new", label: "New Assessment", icon: "M12 4v16m8-8H4" },
  { to: "/history", label: "History", icon: "M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" },
  { to: "/about", label: "About", icon: "M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" },
];

export default function Layout() {
  return (
    <div className="flex min-h-screen bg-gray-50 text-ink">
      <aside className="w-60 bg-gradient-to-b from-[#14161f] to-[#191b26] text-white flex flex-col p-4 fixed top-0 left-0 bottom-0">
        <div className="flex items-center gap-2.5 px-2 pb-6">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-accent to-indigo-400 flex items-center justify-center font-extrabold text-sm shadow-lg shadow-accent/30">
            C
          </div>
          <span className="font-extrabold text-[17px] tracking-tight">ChangeGuard</span>
        </div>
        <nav className="flex flex-col gap-0.5">
          {links.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              end={l.to === "/"}
              className={({ isActive }) =>
                `flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  isActive ? "bg-accent text-white" : "text-white/60 hover:bg-white/5 hover:text-white"
                }`
              }
            >
              <svg className="w-4 h-4 opacity-90" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d={l.icon} />
              </svg>
              {l.label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto pt-4 border-t border-white/10">
          <div className="flex items-center gap-2 px-3 text-[11.5px] text-white/45">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_0_3px_rgba(52,211,153,0.25)]"></span>
            Agent online
          </div>
          <div className="px-3 pt-1.5 text-[10.5px] text-white/25">v1.0 &middot; Agentic Risk Engine</div>
        </div>
      </aside>
      <main className="flex-1 ml-60 px-11 py-9 max-w-[1240px]">
        <Outlet />
      </main>
    </div>
  );
}
