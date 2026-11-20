import { useEffect, useState } from "react";
import { api } from "../api/client";
import { StatusBadge } from "../components/UI";
import type { AuditItem, CommandItem } from "../types";

export function ActivityPage({ mode }: { mode: "commands" | "audit" }) {
  const [commands, setCommands] = useState<CommandItem[]>([]);
  const [audits, setAudits] = useState<AuditItem[]>([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    setErr("");
    if (mode === "commands") {
      api<{ commands: CommandItem[] }>("/api/v1/commands/")
        .then((r) => setCommands(r.commands))
        .catch((e) => setErr(e.message));
    } else {
      api<{ audit_logs: AuditItem[] }>("/api/v1/audit/")
        .then((r) => setAudits(r.audit_logs))
        .catch((e) => setErr(e.message));
    }
  }, [mode]);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">{mode === "commands" ? "Commands" : "Audit Log"}</h1>
        <p className="text-xs text-slate-500">
          {mode === "commands" ? "Command execution and device acknowledgment state" : "Append-only security & activity history"}
        </p>
      </div>
      {err && <div className="bg-red-50 border border-red-200 text-red-700 p-3 rounded-lg text-xs">{err}</div>}
      <div className="bg-white border border-slate-200 rounded-lg overflow-x-auto">
        {mode === "commands" ? (
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-slate-500">
                <th className="p-3">Device</th>
                <th className="p-3">Command</th>
                <th className="p-3">Status</th>
                <th className="p-3">By</th>
                <th className="p-3">Issued</th>
                <th className="p-3">Result</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {commands.map((c) => (
                <tr key={c.id}>
                  <td className="p-3 font-medium">{c.device_model || c.device_identifier}</td>
                  <td className="p-3">{c.command_type}</td>
                  <td className="p-3"><StatusBadge label={c.command_status} /></td>
                  <td className="p-3">{c.created_by ?? "-"}</td>
                  <td className="p-3">{new Date(c.issued_at).toLocaleString()}</td>
                  <td className="p-3">{c.execution_result || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-slate-500">
                <th className="p-3">Time</th>
                <th className="p-3">Actor</th>
                <th className="p-3">Event</th>
                <th className="p-3">Target</th>
                <th className="p-3">IP</th>
                <th className="p-3">Device / Browser</th>
                <th className="p-3">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {audits.map((a) => (
                <tr key={a.id}>
                  <td className="p-3">{new Date(a.timestamp).toLocaleString()}</td>
                  <td className="p-3">{a.actor ?? "system/device"}</td>
                  <td className="p-3 font-medium">{a.event}</td>
                  <td className="p-3">{a.target_type ? `${a.target_type}:${a.target_id.slice(0, 8)}` : "-"}</td>
                  <td className="p-3"><code>{a.source_ip ?? "-"}</code></td>
                  <td className="p-3" title={a.user_agent || ""}>{a.client_device || "-"}</td>
                  <td className="p-3">{a.result || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
