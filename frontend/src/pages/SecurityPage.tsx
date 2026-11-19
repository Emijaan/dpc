import { useEffect, useState } from "react";
import { api } from "../api/client";
import { ConfirmModal, StatusBadge } from "../components/UI";
import type { SigningKeyItem } from "../types";

export function SecurityPage() {
  const [keys, setKeys] = useState<SigningKeyItem[]>([]);
  const [revokeId, setRevokeId] = useState<string | null>(null);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  async function load() {
    setErr("");
    try {
      const r = await api<{ signing_keys: SigningKeyItem[] }>("/api/v1/keys/");
      setKeys(r.signing_keys);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load keys");
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
    </div>
  );
}
