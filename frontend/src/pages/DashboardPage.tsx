import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { StatRow, StatusBadge } from "../components/UI";
import type { AuditItem, CommandItem, DashboardStats, DeviceItem } from "../types";

export function DashboardPage() {
  const { user } = useAuth();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [devices, setDevices] = useState<DeviceItem[]>([]);
  const [commands, setCommands] = useState<CommandItem[]>([]);
  const [audits, setAudits] = useState<AuditItem[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      api<DashboardStats>("/api/v1/dashboard/stats/"),
      api<{ devices: DeviceItem[] }>("/api/v1/devices/?page_size=5"),
      api<{ commands: CommandItem[] }>("/api/v1/commands/").catch(() => ({ commands: [] })),
      api<{ audit_logs: AuditItem[] }>("/api/v1/audit/").catch(() => ({ audit_logs: [] })),
    ])
      .then(([s, d, c, a]) => {
        setStats(s);
        setDevices(d.devices);
        setCommands(c.commands.slice(0, 5));
        setAudits(a.audit_logs.slice(0, 6));
      })
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <div className="bg-red-50 border border-red-200 text-red-700 p-4 rounded-lg">{error}</div>;
  if (!stats) return <div className="text-slate-500">Loading dashboard...</div>;

  const role = user?.account_type ?? "VENDOR";
  const statItems =
    role === "SUPERUSER"
      ? [
          { label: "Retailers", value: stats.retailers_count ?? 0 },
          { label: "Vendors", value: stats.vendors_count ?? 0 },
          { label: "Devices", value: stats.devices.total },
          { label: "Online", value: stats.devices.online },
          { label: "Locked", value: stats.devices.locked },
          { label: "Pending Enroll", value: stats.devices.pending_enrollment },
        ]
      : role === "RETAILER"
      ? [
          { label: "Allocated", value: stats.entitlements.allocated },
          { label: "Distributed", value: stats.entitlements.distributed },
          { label: "Consumed", value: stats.entitlements.consumed },
          { label: "Available", value: stats.entitlements.available ?? "Unlimited" },
          { label: "Active Devices", value: stats.devices.active },
          { label: "Vendors", value: stats.vendors_count ?? 0 },
        ]
      : [
          { label: "Allocated", value: stats.entitlements.allocated },
          { label: "Consumed", value: stats.entitlements.consumed },
          { label: "Available", value: stats.entitlements.available ?? "Unlimited" },
          { label: "Devices", value: stats.devices.total },
          { label: "Online", value: stats.devices.online },
          { label: "Locked", value: stats.devices.locked },
        ];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Dashboard</h1>
          <p className="text-xs text-slate-500">{role} operational overview</p>
        </div>
        <Link
          to="/add-device"
          className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium"
        >
          + Add New Device
        </Link>
      </div>

      <StatRow items={statItems} />

      {(stats.expiring_allocations ?? 0) > 0 && (
        <div className="bg-amber-50 border border-amber-200 text-amber-900 rounded-lg px-4 py-3 text-xs">
          {stats.expiring_allocations} entitlement allocation(s) expire within 30 days. Expired allocations cannot
          register new devices, while existing registered devices continue operating normally.
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="bg-white border border-slate-200 rounded-lg p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-slate-900">Recent Devices</h2>
            <Link to="/devices" className="text-xs text-indigo-600 font-medium hover:underline">
              View all
            </Link>
          </div>
          {devices.length === 0 ? (
            <p className="text-xs text-slate-500 py-6 text-center">No devices in your scope yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-200 text-slate-500">
                    <th className="py-2 pr-2">Model</th>
                    <th className="py-2 pr-2">Customer</th>
                    <th className="py-2 pr-2">Enrollment</th>
                    <th className="py-2">Restriction</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {devices.map((d) => (
                    <tr key={d.id}>
                      <td className="py-2 pr-2 font-medium">{d.manufacturer} {d.model}</td>
                      <td className="py-2 pr-2">{d.customer_name ?? "-"}</td>
                      <td className="py-2 pr-2"><StatusBadge label={d.enrollment_status} /></td>
                      <td className="py-2"><StatusBadge label={d.restriction_status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="bg-white border border-slate-200 rounded-lg p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-slate-900">Recent Commands</h2>
            <Link to="/commands" className="text-xs text-indigo-600 font-medium hover:underline">
              View all
            </Link>
          </div>
          {commands.length === 0 ? (
            <p className="text-xs text-slate-500 py-6 text-center">No commands issued yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-200 text-slate-500">
                    <th className="py-2 pr-2">Device</th>
                    <th className="py-2 pr-2">Command</th>
                    <th className="py-2">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {commands.map((c) => (
                    <tr key={c.id}>
                      <td className="py-2 pr-2">{c.device_model || c.device_identifier}</td>
                      <td className="py-2 pr-2 font-medium">{c.command_type}</td>
                      <td className="py-2"><StatusBadge label={c.command_status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-lg p-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-slate-900">Recent Activity</h2>
          <Link to="/audit" className="text-xs text-indigo-600 font-medium hover:underline">
            Audit Log
          </Link>
        </div>
        {audits.length === 0 ? (
          <p className="text-xs text-slate-500 py-4 text-center">No audit events yet.</p>
        ) : (
          <ul className="divide-y divide-slate-100 text-xs">
            {audits.map((a) => (
              <li key={a.id} className="py-2 flex flex-wrap justify-between gap-2">
                <span>
                  <b className="text-slate-800">{a.event}</b> · {a.actor ?? "system"} {a.result ? `(${a.result})` : ""}
                </span>
                <span className="text-slate-400">{new Date(a.timestamp).toLocaleString()}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
