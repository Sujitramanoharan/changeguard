import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { Users as UsersIcon, UserPlus, Trash2 } from "lucide-react";
import { api } from "../api";

const EMPTY = { username: "", password: "", role: "reviewer" };

export default function Users() {
  const me = api.getStoredUser();
  const isAdmin = me?.role === "admin";
  const [users, setUsers] = useState([]);
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = () =>
    api.listUsers().then(setUsers).catch((e) => setError(e?.message));

  useEffect(() => {
    if (isAdmin) load();
  }, [isAdmin]);

  if (!isAdmin) {
    return <Navigate to="/" replace />;
  }

  const create = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.createUser(form);
      setForm(EMPTY);
      await load();
    } catch (err) {
      setError(err?.message || "Could not create user.");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (username) => {
    if (!window.confirm(`Delete user "${username}"?`)) return;
    setError(null);
    try {
      await api.deleteUser(username);
      await load();
    } catch (err) {
      setError(err?.message || "Could not delete user.");
    }
  };

  const input =
    "w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:bg-white text-slate-800";

  return (
    <div className="animate-in space-y-6 max-w-4xl">
      <div>
        <div className="inline-flex items-center gap-1.5 text-xs font-bold text-indigo-600 uppercase tracking-wider mb-1">
          <UsersIcon className="w-4 h-4" /> Administration
        </div>
        <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900">User Management</h1>
        <p className="text-slate-500 text-sm mt-0.5">
          Reviewers run assessments and record CAB decisions. Admins can also use the autonomous agent and manage users.
        </p>
      </div>

      <form onSubmit={create} className="bg-white rounded-2xl border border-slate-200/80 shadow-xs p-5 grid grid-cols-1 sm:grid-cols-4 gap-3 items-end">
        <label className="text-xs font-bold text-slate-500 uppercase tracking-wider space-y-1.5">
          <span>Username</span>
          <input
            className={input}
            value={form.username}
            onChange={(e) => setForm({ ...form, username: e.target.value })}
            required
            minLength={3}
            pattern="[A-Za-z0-9_.\-]+"
            title="Letters, numbers, dot, dash and underscore only"
          />
        </label>
        <label className="text-xs font-bold text-slate-500 uppercase tracking-wider space-y-1.5">
          <span>Password</span>
          <input
            type="password"
            className={input}
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
            required
            minLength={8}
          />
        </label>
        <label className="text-xs font-bold text-slate-500 uppercase tracking-wider space-y-1.5">
          <span>Role</span>
          <select
            className={input}
            value={form.role}
            onChange={(e) => setForm({ ...form, role: e.target.value })}
          >
            <option value="reviewer">reviewer</option>
            <option value="admin">admin</option>
          </select>
        </label>
        <button
          type="submit"
          disabled={busy}
          className="px-4 py-2.5 rounded-xl text-sm font-semibold bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white flex items-center justify-center gap-2"
        >
          <UserPlus className="w-4 h-4" />
          Add user
        </button>
      </form>

      {error && (
        <p className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded-xl p-3">{error}</p>
      )}

      <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs overflow-hidden">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="bg-slate-50/80 border-b border-slate-200 text-slate-400 font-bold uppercase tracking-wider">
              <th className="px-5 py-3">Username</th>
              <th className="px-5 py-3">Role</th>
              <th className="px-5 py-3">Created</th>
              <th className="px-5 py-3 text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {users.map((u) => (
              <tr key={u.id}>
                <td className="px-5 py-3 font-semibold text-slate-900">
                  {u.username}
                  {u.username === me.username && <span className="ml-2 text-[10px] text-slate-400">(you)</span>}
                </td>
                <td className="px-5 py-3 uppercase text-[11px] font-bold text-slate-600">{u.role}</td>
                <td className="px-5 py-3 font-mono text-slate-500">{u.created_at}</td>
                <td className="px-5 py-3 text-right">
                  {u.username !== me.username && (
                    <button
                      type="button"
                      onClick={() => remove(u.username)}
                      className="inline-flex items-center gap-1 text-rose-600 hover:text-rose-700 font-semibold"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                      Delete
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
