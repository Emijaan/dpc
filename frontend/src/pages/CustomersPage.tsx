import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { CustomerItem } from "../types";

export function CustomersPage() {
  const [customers, setCustomers] = useState<CustomerItem[]>([]);
  const [q, setQ] = useState("");
  const [revealed, setRevealed] = useState<{ id: string; full_name: string; mobile: string; email: string } | null>(null);
  const [err, setErr] = useState("");

  async function load(search = q) {
    setErr("");
    try {
      const r = await api<{ customers: CustomerItem[] }>(`/api/v1/customers/?q=${encodeURIComponent(search)}`);
      setCustomers(r.customers);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load customers");
    }
  }

  useEffect(() => {
    load("");
  }, []);

  async function revealCustomer(id: string) {
    try {
      const r = await api<{ id: string; full_name: string; mobile: string; email: string }>(`/api/v1/customers/${id}/reveal/`);
      setRevealed(r);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Reveal failed");
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Customers</h1>
        <p className="text-xs text-slate-500">Mobile numbers and emails are encrypted at rest and masked by default</p>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          load(q);
        }}
        className="flex gap-2"
      >
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search customer name or exact mobile/email..."
          className="max-w-sm w-full rounded-lg border border-slate-300 px-3 py-2 text-sm bg-white"
        />
        <button className="px-4 py-2 rounded-lg border border-slate-300 bg-white text-sm font-medium hover:bg-slate-50">
          Search
        </button>
      </form>

      {err && <div className="bg-red-50 border border-red-200 text-red-700 p-3 rounded-lg text-xs">{err}</div>}
      {revealed && (
        <div className="bg-indigo-50 border border-indigo-200 rounded-lg p-3 text-xs flex justify-between items-center">
          <span>
            <b>{revealed.full_name}</b> · Mobile: <code>{revealed.mobile || "-"}</code> · Email: <code>{revealed.email || "-"}</code> (audited)
          </span>
          <button onClick={() => setRevealed(null)} className="text-indigo-700 font-medium">Hide</button>
        </div>
      )}

      <div className="bg-white border border-slate-200 rounded-lg overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50 text-slate-500">
              <th className="p-3">Full Name</th>
              <th className="p-3">Mobile</th>
              <th className="p-3">Email</th>
              <th className="p-3">Devices</th>
              <th className="p-3">Created</th>
              <th className="p-3">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {customers.length === 0 ? (
              <tr><td colSpan={6} className="p-6 text-center text-slate-500">No customers found.</td></tr>
            ) : (
              customers.map((c) => (
                <tr key={c.id}>
                  <td className="p-3 font-medium text-slate-900">{c.full_name}</td>
                  <td className="p-3"><code>{c.mobile_masked || "-"}</code></td>
                  <td className="p-3"><code>{c.email_masked || "-"}</code></td>
                  <td className="p-3">{c.device_count}</td>
                  <td className="p-3">{new Date(c.created_at).toLocaleDateString()}</td>
                  <td className="p-3">
                    <button onClick={() => revealCustomer(c.id)} className="px-2.5 py-1 rounded border border-slate-300 hover:bg-slate-50">
                      Reveal
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
