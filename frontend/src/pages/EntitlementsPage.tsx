import React, { useEffect, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { StatRow, StatusBadge } from "../components/UI";
import type { AllocationItem, ConsumptionItem, RetailerItem, TransferItem, VendorItem } from "../types";

export function EntitlementsPage() {
  const { user } = useAuth();
  const role = user?.account_type ?? "VENDOR";
  const [bal, setBal] = useState({ allocated: 0, distributed: 0, consumed: 0, available: 0 as number | null, expired: 0 });
  const [allocs, setAllocs] = useState<AllocationItem[]>([]);
  const [transfers, setTransfers] = useState<TransferItem[]>([]);
  const [consumptions, setConsumptions] = useState<ConsumptionItem[]>([]);
  const [recipients, setRecipients] = useState<Array<{ id: number; label: string }>>([]);
  const [recipientId, setRecipientId] = useState("");
  const [qty, setQty] = useState("5");
  const [reason, setReason] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  async function load() {
    setErr("");
    try {
      const [b, h, c] = await Promise.all([
        api<typeof bal>("/api/v1/entitlements/balance/"),
        api<{ allocations: AllocationItem[]; transfers: TransferItem[] }>("/api/v1/entitlements/history/"),
        api<{ consumptions: ConsumptionItem[] }>("/api/v1/entitlements/consumption/"),
      ]);
      setBal(b);
      setAllocs(h.allocations);
      setTransfers(h.transfers);
      setConsumptions(c.consumptions);

      if (role === "SUPERUSER") {
        const [r, v] = await Promise.all([
          api<{ retailers: RetailerItem[] }>("/api/v1/retailers/"),
          api<{ vendors: VendorItem[] }>("/api/v1/vendors/"),
        ]);
        setRecipients([
          ...r.retailers.map((x) => ({ id: x.account_id, label: `Retailer: ${x.business_name} (${x.username})` })),
          ...v.vendors.map((x) => ({ id: x.account_id, label: `Vendor: ${x.business_name} (${x.username})` })),
        ]);
      } else if (role === "RETAILER") {
        const v = await api<{ vendors: VendorItem[] }>("/api/v1/vendors/");
        setRecipients(v.vendors.map((x) => ({ id: x.account_id, label: `${x.business_name} (${x.username})` })));
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Load failed");
    }
  }

  useEffect(() => {
    load();
  }, [role]);

  async function handleAction(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    setMsg("");
    try {
      if (role === "VENDOR") {
        await api("/api/v1/entitlements/transfer/", {
          method: "POST",
          body: JSON.stringify({ receiver_id: Number(recipientId), quantity: Number(qty), reason }),
        });
        setMsg("Unused entitlements transferred.");
      } else {
        await api("/api/v1/entitlements/allocate/", {
          method: "POST",
          body: JSON.stringify({ recipient_id: Number(recipientId), quantity: Number(qty), notes: reason }),
        });
        setMsg("Entitlements allocated (365-day validity).");
      }
      setReason("");
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Operation failed");
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Entitlements</h1>
        <p className="text-xs text-slate-500">One entitlement = one successfully registered device (365-day validity)</p>
      </div>

      <StatRow
        items={[
          { label: "Allocated", value: bal.allocated },
          { label: "Distributed", value: bal.distributed },
          { label: "Consumed", value: bal.consumed },
          { label: "Available", value: bal.available ?? "Unlimited" },
          { label: "Expired", value: bal.expired },
        ]}
      />

      {err && <div className="bg-red-50 border border-red-200 text-red-700 p-3 rounded-lg text-xs">{err}</div>}
      {msg && <div className="bg-green-50 border border-green-200 text-green-700 p-3 rounded-lg text-xs">{msg}</div>}

      <form onSubmit={handleAction} className="bg-white border border-slate-200 rounded-lg p-4 space-y-3">
        <h2 className="text-sm font-semibold text-slate-900">
          {role === "SUPERUSER" ? "Allocate Entitlements" : role === "RETAILER" ? "Distribute to Vendor" : "Transfer Unused Entitlements to Same-Retailer Vendor"}
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {role === "VENDOR" ? (
            <input
              required
              type="number"
              placeholder="Recipient Vendor Account ID"
              value={recipientId}
              onChange={(e) => setRecipientId(e.target.value)}
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          ) : (
            <select
              required
              value={recipientId}
              onChange={(e) => setRecipientId(e.target.value)}
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
            >
              <option value="">-- Select Recipient --</option>
              {recipients.map((r) => (
                <option key={r.id} value={r.id}>{r.label}</option>
              ))}
            </select>
          )}
          <input
            required
            type="number"
            min={1}
            placeholder="Quantity"
            value={qty}
            onChange={(e) => setQty(e.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
          <input
            placeholder="Notes / Reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
        </div>
        <button className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium">
          {role === "VENDOR" ? "Transfer" : "Allocate"}
        </button>
      </form>

      <div className="bg-white border border-slate-200 rounded-lg overflow-x-auto">
        <div className="px-4 py-3 border-b border-slate-200 font-semibold text-sm">Allocations</div>
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50 text-slate-500">
              <th className="p-3">Account</th>
              <th className="p-3">Issued</th>
              <th className="p-3">Expires</th>
              <th className="p-3">Qty</th>
              <th className="p-3">Used</th>
              <th className="p-3">Available</th>
              <th className="p-3">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {allocs.map((a) => (
              <tr key={a.id}>
                <td className="p-3 font-medium">{a.allocated_to_username}</td>
                <td className="p-3">{new Date(a.issued_at).toLocaleDateString()}</td>
                <td className="p-3">{new Date(a.expires_at).toLocaleDateString()}</td>
                <td className="p-3">{a.allocated_quantity}</td>
                <td className="p-3">{a.consumed_quantity}</td>
                <td className="p-3">{a.available_quantity}</td>
                <td className="p-3"><StatusBadge label={a.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="bg-white border border-slate-200 rounded-lg overflow-x-auto">
          <div className="px-4 py-3 border-b border-slate-200 font-semibold text-sm">Transfer History</div>
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-slate-500">
                <th className="p-3">From → To</th>
                <th className="p-3">Qty</th>
                <th className="p-3">When</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {transfers.map((t) => (
                <tr key={t.id}>
                  <td className="p-3">{t.sender_username} → {t.receiver_username}</td>
                  <td className="p-3">{t.quantity}</td>
                  <td className="p-3">{new Date(t.transfer_date).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="bg-white border border-slate-200 rounded-lg overflow-x-auto">
          <div className="px-4 py-3 border-b border-slate-200 font-semibold text-sm">Consumption Ledger (Append-only)</div>
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-slate-500">
                <th className="p-3">Reference</th>
                <th className="p-3">Device</th>
                <th className="p-3">Consumed</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {consumptions.map((c) => (
                <tr key={c.id}>
                  <td className="p-3 font-medium">{c.registration_reference}</td>
                  <td className="p-3"><code>{c.device_identifier}</code></td>
                  <td className="p-3">{new Date(c.consumed_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
