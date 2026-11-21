import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { ConfirmModal, StatusBadge } from "../components/UI";
import type { AccountAccessItem, SigningKeyItem } from "../types";

export function SecurityPage() {
  const { user } = useAuth();
  const [keys, setKeys] = useState<SigningKeyItem[]>([]);
  const [accounts, setAccounts] = useState<AccountAccessItem[]>([]);
  const [frpInput, setFrpInput] = useState("");
  const [effectiveFrp, setEffectiveFrp] = useState<string[]>([]);
  const [savingFrp, setSavingFrp] = useState(false);
  const [revokeId, setRevokeId] = useState<string | null>(null);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  async function load() {
    setErr("");
    try {
      const [k, a, frp] = await Promise.all([
        api<{ signing_keys: SigningKeyItem[] }>("/api/v1/keys/"),
        api<{ accounts: AccountAccessItem[] }>("/api/v1/accounts/"),
        api<{ account_ids: string[]; effective_account_ids: string[] }>("/api/v1/devices/frp-policy/"),
      ]);
      setKeys(k.signing_keys);
      setAccounts(a.accounts);
      setFrpInput(frp.account_ids.join(", "));
      setEffectiveFrp(frp.effective_account_ids);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load security data");
    }
  }

  async function saveFrp(e: React.FormEvent) {
    e.preventDefault();
    setSavingFrp(true);
    setErr("");
    setMsg("");
    try {
      const r = await api<{ account_ids: string[]; effective_account_ids: string[] }>("/api/v1/devices/frp-policy/", {
        method: "PUT",
        body: JSON.stringify({ account_ids: frpInput }),
      });
      setFrpInput(r.account_ids.join(", "));
      setEffectiveFrp(r.effective_account_ids);
      setMsg("Enterprise FRP Google Account IDs saved. Enrolled Android 11+ devices apply this automatically on sync.");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to save FRP policy");
    } finally {
      setSavingFrp(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function rotateKey() {
    setErr("");
    setMsg("");
    try {
      await api("/api/v1/keys/rotate/", { method: "POST", body: JSON.stringify({ category: "COMMAND" }) });
      setMsg("Command signing key rotated.");
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Rotation failed");
    }
  }

  async function revokeKey(id: string) {
    setErr("");
    setMsg("");
    try {
      await api(`/api/v1/keys/${id}/revoke/`, { method: "POST", body: JSON.stringify({ reason: "operator_revoked" }) });
      setMsg("Signing key revoked.");
      setRevokeId(null);
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Revoke failed");
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Cryptographic Signing Keys</h1>
          <p className="text-xs text-slate-500">Command-signing public key metadata only — private keys never leave the server</p>
        </div>
        <button onClick={rotateKey} className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium">
          Rotate Command Key
        </button>
      </div>
      {err && <div className="bg-red-50 border border-red-200 text-red-700 p-3 rounded-lg text-xs">{err}</div>}
      {msg && <div className="bg-green-50 border border-green-200 text-green-700 p-3 rounded-lg text-xs">{msg}</div>}
      <div className="bg-white border border-slate-200 rounded-lg overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50 text-slate-500">
              <th className="p-3">Key ID</th>
              <th className="p-3">Category</th>
              <th className="p-3">Algorithm</th>
              <th className="p-3">Version</th>
              <th className="p-3">Status</th>
              <th className="p-3">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {keys.map((k) => (
              <tr key={k.key_id}>
                <td className="p-3"><code>{k.key_id}</code></td>
                <td className="p-3">{k.category}</td>
                <td className="p-3">{k.algorithm}</td>
                <td className="p-3">v{k.version}</td>
                <td className="p-3"><StatusBadge label={k.status} /></td>
                <td className="p-3">
                  {k.status !== "REVOKED" && (
                    <button onClick={() => setRevokeId(k.key_id)} className="px-2.5 py-1 rounded border border-red-300 text-red-700">
                      Revoke
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ConfirmModal
        open={Boolean(revokeId)}
        title="Revoke Signing Key?"
        message="Devices will immediately reject commands signed by a revoked key."
        confirmLabel="Revoke Key"
        danger
        onCancel={() => setRevokeId(null)}
        onConfirm={() => (revokeId ? revokeKey(revokeId) : Promise.resolve())}
      />

      <div className="bg-white border border-slate-200 rounded-lg p-4 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">Enterprise Factory Reset Protection (FRP — Android 11+)</h2>
            <p className="text-xs text-slate-500">
              Locks devices to your company Google account(s) even after a hardware recovery wipe. Requires 21-digit numeric Google Account ID(s), comma-separated (not email addresses).
            </p>
          </div>
          <StatusBadge label={effectiveFrp.length > 0 ? `ACTIVE (${effectiveFrp.length})` : "NOT CONFIGURED"} variant={effectiveFrp.length > 0 ? "success" : "warning"} />
        </div>
        <form onSubmit={saveFrp} className="flex flex-wrap gap-2">
          <input
            value={frpInput}
            onChange={(e) => setFrpInput(e.target.value)}
            disabled={user?.account_type !== "SUPERUSER"}
            placeholder="e.g. 103948271645091827364"
            className="flex-1 min-w-[260px] rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-mono disabled:bg-slate-50"
          />
          {user?.account_type === "SUPERUSER" && (
            <button
              type="submit"
              disabled={savingFrp}
              className="px-4 py-1.5 rounded-lg bg-slate-900 text-white text-xs font-medium disabled:opacity-50"
            >
              {savingFrp ? "Saving..." : "Save FRP Policy"}
            </button>
          )}
        </form>
      </div>

      <div className="bg-white border border-slate-200 rounded-lg overflow-x-auto">
        <div className="px-4 py-3 border-b border-slate-200 font-semibold text-sm">All User Access (IP Address &amp; Device)</div>
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50 text-slate-500">
              <th className="p-3">Username</th>
              <th className="p-3">Type</th>
              <th className="p-3">Last IP Address</th>
              <th className="p-3">Device / Browser</th>
              <th className="p-3">Last Active</th>
              <th className="p-3">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {accounts.map((u) => (
              <tr key={u.id}>
                <td className="p-3 font-medium text-slate-900">{u.username}</td>
                <td className="p-3"><StatusBadge label={u.account_type ?? "STAFF"} variant="info" /></td>
                <td className="p-3"><code>{u.last_ip || "-"}</code></td>
                <td className="p-3" title={u.last_user_agent || ""}>{u.last_device || "-"}</td>
                <td className="p-3">{u.last_active_at ? new Date(u.last_active_at).toLocaleString() : "Never"}</td>
                <td className="p-3"><StatusBadge label={u.is_active ? "ACTIVE" : "INACTIVE"} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
