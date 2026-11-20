import React, { useEffect, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { ConfirmModal, StatusBadge } from "../components/UI";
import type { RetailerItem, VendorItem } from "../types";

export function TenantsPage({ mode }: { mode: "retailers" | "vendors" }) {
  const { user } = useAuth();
  const [retailers, setRetailers] = useState<RetailerItem[]>([]);
  const [vendors, setVendors] = useState<VendorItem[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [editing, setEditing] = useState<RetailerItem | VendorItem | null>(null);
  const [editForm, setEditForm] = useState({
    full_name: "",
    business_name: "",
    contact_person: "",
    address: "",
    mobile: "",
    email: "",
  });
  const [confirmTarget, setConfirmTarget] = useState<{
    item: RetailerItem | VendorItem;
    action: "disable" | "enable" | "delete";
  } | null>(null);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  const [form, setForm] = useState({
    username: "",
    password: "",
    full_name: "",
    business_name: "",
    contact_person: "",
    address: "",
    mobile: "",
    email: "",
    entitlement_quota: "10",
    retailer_profile_id: "",
  });

  async function load() {
    setErr("");
    try {
      if (mode === "retailers") {
        const r = await api<{ retailers: RetailerItem[] }>("/api/v1/retailers/");
        setRetailers(r.retailers);
      } else {
        const v = await api<{ vendors: VendorItem[] }>("/api/v1/vendors/");
        setVendors(v.vendors);
        if (user?.account_type === "SUPERUSER") {
          const r = await api<{ retailers: RetailerItem[] }>("/api/v1/retailers/");
          setRetailers(r.retailers);
        }
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load");
    }
  }

  useEffect(() => {
    setEditing(null);
    setConfirmTarget(null);
    load();
  }, [mode]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    setMsg("");
    try {
      const payload: Record<string, unknown> = {
        username: form.username.trim(),
        password: form.password,
        full_name: form.full_name.trim(),
        business_name: form.business_name.trim(),
        contact_person: form.contact_person.trim(),
        address: form.address.trim(),
        mobile: form.mobile.trim(),
        email: form.email.trim(),
        entitlement_quota: form.entitlement_quota ? Number(form.entitlement_quota) : null,
      };
      if (mode === "vendors" && user?.account_type === "SUPERUSER") {
        payload.retailer_profile_id = form.retailer_profile_id;
      }
      await api(mode === "retailers" ? "/api/v1/retailers/" : "/api/v1/vendors/", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setShowCreate(false);
      setForm({
        username: "", password: "", full_name: "", business_name: "",
        contact_person: "", address: "", mobile: "", email: "",
        entitlement_quota: "10", retailer_profile_id: "",
      });
      setMsg(`${mode === "retailers" ? "Retailer" : "Vendor"} created.`);
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Create failed");
    }
  }

  function startEdit(item: RetailerItem | VendorItem) {
    setEditing(item);
    setEditForm({
      full_name: item.full_name,
      business_name: item.business_name,
      contact_person: item.contact_person,
      address: item.address,
      mobile: item.mobile,
      email: item.email,
    });
  }

  async function handleEditSave(e: React.FormEvent) {
    e.preventDefault();
    if (!editing) return;
    setErr("");
    setMsg("");
    try {
      const base = mode === "retailers" ? "/api/v1/retailers" : "/api/v1/vendors";
      await api(`${base}/${editing.id}/`, {
        method: "PATCH",
        body: JSON.stringify(editForm),
      });
      setEditing(null);
      setMsg("Account updated.");
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Update failed");
    }
  }

  async function executeConfirm() {
    if (!confirmTarget) return;
    setErr("");
    setMsg("");
    const { item, action } = confirmTarget;
    try {
      if (action === "delete") {
        const base = mode === "retailers" ? "/api/v1/retailers" : "/api/v1/vendors";
        const res = await api<{ status?: string; message?: string } | undefined>(`${base}/${item.id}/`, {
          method: "DELETE",
        });
        setMsg(res?.message ?? `${item.business_name} deleted.`);
      } else {
        await api(`/api/v1/accounts/${item.account_id}/${action === "disable" ? "deactivate" : "activate"}/`, {
          method: "POST",
        });
        setMsg(
          action === "disable"
            ? mode === "retailers"
              ? `${item.business_name} and its unallocated entitlements disabled. Vendor-allocated entitlements remain valid.`
              : `${item.business_name} disabled and all its unused entitlements invalidated.`
            : `${item.business_name} activated.`
        );
      }
      setConfirmTarget(null);
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Action failed");
      setConfirmTarget(null);
    }
  }

  const rows = mode === "retailers" ? retailers : vendors;
  const title = mode === "retailers" ? "Retailers" : "Vendors";

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">{title}</h1>
          <p className="text-xs text-slate-500">
            {mode === "retailers" ? "Manage distributor / finance partners" : "Manage authorized vendors"}
          </p>
        </div>
        <button
          onClick={() => setShowCreate((v) => !v)}
          className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium"
        >
          + New {mode === "retailers" ? "Retailer" : "Vendor"}
        </button>
      </div>

      {err && <div className="bg-red-50 border border-red-200 text-red-700 p-3 rounded-lg text-xs">{err}</div>}
      {msg && <div className="bg-green-50 border border-green-200 text-green-700 p-3 rounded-lg text-xs">{msg}</div>}

      {showCreate && (
        <form onSubmit={handleCreate} className="bg-white border border-slate-200 rounded-lg p-5 space-y-3">
          <h2 className="text-sm font-semibold text-slate-900">Create {mode === "retailers" ? "Retailer" : "Vendor"}</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            <input required placeholder="Username *" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} className="rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            <input required type="password" minLength={8} placeholder="Password (min 8) *" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} className="rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            <input required placeholder="Full Name *" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} className="rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            <input required placeholder="Business / Shop Name *" value={form.business_name} onChange={(e) => setForm({ ...form, business_name: e.target.value })} className="rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            <input required placeholder="Contact Person *" value={form.contact_person} onChange={(e) => setForm({ ...form, contact_person: e.target.value })} className="rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            <input required placeholder="Mobile *" value={form.mobile} onChange={(e) => setForm({ ...form, mobile: e.target.value })} className="rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            <input required type="email" placeholder="Email *" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className="rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            <input placeholder="Address" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} className="rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            <input type="number" min={0} placeholder="Initial Entitlements" value={form.entitlement_quota} onChange={(e) => setForm({ ...form, entitlement_quota: e.target.value })} className="rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            {mode === "vendors" && user?.account_type === "SUPERUSER" && (
              <select
                required
                value={form.retailer_profile_id}
                onChange={(e) => setForm({ ...form, retailer_profile_id: e.target.value })}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
              >
                <option value="">-- Select Parent Retailer --</option>
                {retailers.map((r) => (
                  <option key={r.id} value={r.id}>{r.business_name} ({r.username})</option>
                ))}
              </select>
            )}
          </div>
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setShowCreate(false)} className="px-3 py-1.5 rounded-lg border border-slate-300 text-sm">Cancel</button>
            <button type="submit" className="px-4 py-1.5 rounded-lg bg-indigo-600 text-white text-sm font-medium">Create</button>
          </div>
        </form>
      )}

      {editing && (
        <form onSubmit={handleEditSave} className="bg-white border border-indigo-200 rounded-lg p-5 space-y-3">
          <h2 className="text-sm font-semibold text-slate-900">Edit {editing.business_name} ({editing.username})</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            <input required placeholder="Full Name *" value={editForm.full_name} onChange={(e) => setEditForm({ ...editForm, full_name: e.target.value })} className="rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            <input required placeholder="Business Name *" value={editForm.business_name} onChange={(e) => setEditForm({ ...editForm, business_name: e.target.value })} className="rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            <input required placeholder="Contact Person *" value={editForm.contact_person} onChange={(e) => setEditForm({ ...editForm, contact_person: e.target.value })} className="rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            <input required placeholder="Mobile *" value={editForm.mobile} onChange={(e) => setEditForm({ ...editForm, mobile: e.target.value })} className="rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            <input required type="email" placeholder="Email *" value={editForm.email} onChange={(e) => setEditForm({ ...editForm, email: e.target.value })} className="rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            <input placeholder="Address" value={editForm.address} onChange={(e) => setEditForm({ ...editForm, address: e.target.value })} className="rounded-lg border border-slate-300 px-3 py-2 text-sm" />
          </div>
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setEditing(null)} className="px-3 py-1.5 rounded-lg border border-slate-300 text-sm">Cancel</button>
            <button type="submit" className="px-4 py-1.5 rounded-lg bg-indigo-600 text-white text-sm font-medium">Save Changes</button>
          </div>
        </form>
      )}

      <div className="bg-white border border-slate-200 rounded-lg overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-slate-200 text-slate-500 bg-slate-50">
              <th className="p-3">Business</th>
              <th className="p-3">Username</th>
              {mode === "vendors" && <th className="p-3">Retailer</th>}
              <th className="p-3">Contact</th>
              <th className="p-3">Entitlements</th>
              <th className="p-3">Last IP &amp; Device</th>
              <th className="p-3">Status</th>
              <th className="p-3">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.length === 0 ? (
              <tr><td colSpan={8} className="p-6 text-center text-slate-500">No records found.</td></tr>
            ) : (
              rows.map((r) => (
                <tr key={r.id}>
                  <td className="p-3 font-medium text-slate-900">{r.business_name}</td>
                  <td className="p-3">{r.username}</td>
                  {mode === "vendors" && <td className="p-3">{(r as VendorItem).retailer_business_name}</td>}
                  <td className="p-3">{r.contact_person} · {r.mobile}</td>
                  <td className="p-3">{r.entitlements_consumed} / {r.entitlement_quota ?? "Unlimited"}</td>
                  <td className="p-3">
                    <div><code>{r.last_ip || "-"}</code></div>
                    <div className="text-slate-500">{r.last_device || "-"}</div>
                  </td>
                  <td className="p-3"><StatusBadge label={r.status} /></td>
                  <td className="p-3 flex flex-wrap gap-1.5">
                    <button
                      onClick={() => startEdit(r)}
                      className="px-2.5 py-1 rounded border border-slate-300 hover:bg-slate-50 font-medium"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => setConfirmTarget({ item: r, action: r.is_active ? "disable" : "enable" })}
                      className="px-2.5 py-1 rounded border border-slate-300 hover:bg-slate-50 font-medium"
                    >
                      {r.is_active ? "Disable" : "Enable"}
                    </button>
                    <button
                      onClick={() => setConfirmTarget({ item: r, action: "delete" })}
                      className="px-2.5 py-1 rounded border border-red-300 text-red-700 hover:bg-red-50 font-medium"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <ConfirmModal
        open={Boolean(confirmTarget)}
        title={
          confirmTarget?.action === "delete"
            ? `Delete ${confirmTarget.item.business_name}?`
            : confirmTarget?.action === "disable"
            ? `Disable ${confirmTarget.item.business_name}?`
            : `Enable ${confirmTarget?.item.business_name}?`
        }
        message={
          confirmTarget?.action === "disable"
            ? mode === "retailers"
              ? "Disabling this Retailer will disable its own unallocated keys. Keys already allocated to its Vendors will stay valid."
              : "Disabling this Vendor will make all of its remaining keys invalid and revoke pending enrollments."
            : confirmTarget?.action === "delete"
            ? mode === "retailers"
              ? "Deleting this Retailer will disable its own unallocated keys. Keys already allocated to Vendors will NOT be disabled or released."
              : "Deletes this Vendor (or disables it and invalidates its keys if it has existing device history)."
            : "Re-enables this account for login."
        }
        confirmLabel={confirmTarget?.action.toUpperCase()}
        danger={confirmTarget?.action !== "enable"}
        onCancel={() => setConfirmTarget(null)}
        onConfirm={executeConfirm}
      />
    </div>
  );
}
