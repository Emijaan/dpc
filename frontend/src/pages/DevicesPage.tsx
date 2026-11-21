import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, downloadAuthorizedFile } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { ConfirmModal, StatusBadge } from "../components/UI";
import type { DeviceItem } from "../types";

export function DevicesPage() {
  const { user } = useAuth();
  const [devices, setDevices] = useState<DeviceItem[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [enrollmentStatus, setEnrollmentStatus] = useState("");
  const [restrictionStatus, setRestrictionStatus] = useState("");
  const [androidVersion, setAndroidVersion] = useState("");
  const [selected, setSelected] = useState<DeviceItem | null>(null);
  const [revealedImei, setRevealedImei] = useState("");
  const [photoData, setPhotoData] = useState<{ photo_b64: string; captured_at: string | null } | null>(null);
  const [confirmAction, setConfirmAction] = useState<"lock" | "unlock" | "release" | null>(null);
  const [editLock, setEditLock] = useState({
    emi_amount: "",
    emi_due_date: "",
    pending_emi_count: "",
    dealer_name: "",
    dealer_mobile: "",
    dealer_company: "",
  });
  const [savingLock, setSavingLock] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  async function load(targetPage = page) {
    setErr("");
    const params = new URLSearchParams({ page: String(targetPage), page_size: "25" });
    if (q.trim()) params.set("q", q.trim());
    if (enrollmentStatus) params.set("enrollment_status", enrollmentStatus);
    if (restrictionStatus) params.set("restriction_status", restrictionStatus);
    if (androidVersion.trim()) params.set("android_version", androidVersion.trim());
    try {
      const r = await api<{ count: number; page: number; devices: DeviceItem[] }>(`/api/v1/devices/?${params}`);
      setDevices(r.devices);
      setCount(r.count);
      setPage(r.page);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load devices");
    }
  }

  useEffect(() => {
    load(1);
  }, [enrollmentStatus, restrictionStatus]);

  async function runCommand(
    dev: DeviceItem,
    action: "lock" | "unlock" | "sync-command" | "release" | "locate" | "capture-photo" | "camera" | "gps-policy" | "network-policy" | "update-agent",
    payload?: Record<string, unknown>
  ) {
    setErr("");
    setMsg("");
    try {
      const r = await api<{ status: string; device_online: boolean }>(`/api/v1/devices/${dev.id}/${action}/`, {
        method: "POST",
        body: JSON.stringify({ reason: "operator_console", ...(payload ?? {}) }),
      });
      setMsg(
        r.device_online
          ? `Command ${action.toUpperCase()} issued (${r.status}).`
          : `Device is offline. Command queued (${r.status}) — waiting for device acknowledgment.`
      );
      setConfirmAction(null);
      if (action === "lock" || action === "unlock" || action === "release") {
        setSelected(null);
      }
      await load(page);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Command failed");
    }
  }

  async function viewPhoto(dev: DeviceItem) {
    setErr("");
    try {
      const r = await api<{ photo_b64: string; captured_at: string | null }>(`/api/v1/devices/${dev.id}/photo/`);
      setPhotoData(r);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load photo");
    }
  }

  async function revealImei(dev: DeviceItem) {
    try {
      const r = await api<{ imei: string }>(`/api/v1/devices/${dev.id}/reveal-imei/`);
      setRevealedImei(r.imei || "(not recorded)");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Reveal failed");
    }
  }

  function openManage(d: DeviceItem) {
    setSelected(d);
    setRevealedImei("");
    setPhotoData(null);
    setEditLock({
      emi_amount: d.emi_amount || "",
      emi_due_date: d.emi_due_date || "",
      pending_emi_count: d.pending_emi_count || "",
      dealer_name: d.dealer_name || "",
      dealer_mobile: d.dealer_mobile || "",
      dealer_company: d.dealer_company || "",
    });
  }

  async function saveLockDetails(e: React.FormEvent) {
    e.preventDefault();
    if (!selected) return;
    setSavingLock(true);
    setErr("");
    setMsg("");
    try {
      const r = await api<{ device: DeviceItem }>(`/api/v1/devices/${selected.id}/`, {
        method: "PATCH",
        body: JSON.stringify(editLock),
      });
      setSelected(r.device);
      setMsg("Lock-screen EMI & dealer details updated (syncs automatically on next device poll).");
      await load(page);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to save lock-screen details");
    } finally {
      setSavingLock(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Devices ({count})</h1>
          <p className="text-xs text-slate-500">Scoped to {user?.account_type} ownership boundaries</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => downloadAuthorizedFile("/api/v1/devices/export/", "devices_export.csv")}
            className="px-3 py-2 rounded-lg border border-slate-300 bg-white text-sm font-medium hover:bg-slate-50"
          >
            Export CSV
          </button>
          <Link to="/add-device" className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium">
            + Add Device
          </Link>
        </div>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          load(1);
        }}
        className="flex flex-wrap gap-2 bg-white border border-slate-200 rounded-lg p-3"
      >
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search ref, model, customer, exact IMEI..."
          className="flex-1 min-w-[200px] rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
        />
        <select value={enrollmentStatus} onChange={(e) => setEnrollmentStatus(e.target.value)} className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm">
          <option value="">All Enrollment</option>
          <option value="PENDING">PENDING</option>
          <option value="ENROLLED">ENROLLED</option>
          <option value="FAILED">FAILED</option>
          <option value="RELEASED">RELEASED</option>
        </select>
        <select value={restrictionStatus} onChange={(e) => setRestrictionStatus(e.target.value)} className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm">
          <option value="">All Restrictions</option>
          <option value="NONE">NONE</option>
          <option value="LOCK_PENDING">LOCK_PENDING</option>
          <option value="LOCKED">LOCKED</option>
          <option value="UNLOCK_PENDING">UNLOCK_PENDING</option>
        </select>
        <input
          value={androidVersion}
          onChange={(e) => setAndroidVersion(e.target.value)}
          placeholder="Android ver"
          className="w-28 rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
        />
        <button className="px-4 py-1.5 rounded-lg bg-slate-900 text-white text-sm font-medium">Filter</button>
      </form>

      {err && <div className="bg-red-50 border border-red-200 text-red-700 p-3 rounded-lg text-xs">{err}</div>}
      {msg && <div className="bg-green-50 border border-green-200 text-green-700 p-3 rounded-lg text-xs">{msg}</div>}

      <div className="bg-white border border-slate-200 rounded-lg overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50 text-slate-500">
              <th className="p-3">Ref / Device</th>
              <th className="p-3">Customer</th>
              <th className="p-3">IMEI</th>
              <th className="p-3">Owner</th>
              <th className="p-3">Connection</th>
              <th className="p-3">Enrollment</th>
              <th className="p-3">Restriction</th>
              <th className="p-3">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {devices.length === 0 ? (
              <tr><td colSpan={8} className="p-6 text-center text-slate-500">No devices match your filters.</td></tr>
            ) : (
              devices.map((d) => (
                <tr key={d.id}>
                  <td className="p-3">
                    <div className="font-medium text-slate-900">{d.manufacturer} {d.model}</div>
                    <div className="text-slate-500">{d.registration_reference || d.device_identifier.slice(0, 14)} · Android {d.android_version || "?"}</div>
                  </td>
                  <td className="p-3">{d.customer_name ?? "-"}</td>
                  <td className="p-3"><code>{d.imei_masked || "-"}</code></td>
                  <td className="p-3">{d.vendor_username ?? d.retailer_username ?? "Platform"}</td>
                  <td className="p-3"><StatusBadge label={d.connection_status} /></td>
                  <td className="p-3"><StatusBadge label={d.enrollment_status} /></td>
                  <td className="p-3"><StatusBadge label={d.restriction_status} /></td>
                  <td className="p-3 flex flex-wrap gap-1.5">
                    <button
                      onClick={() => openManage(d)}
                      className="px-2.5 py-1 rounded border border-slate-300 hover:bg-slate-50 font-medium"
                    >
                      Manage
                    </button>
                    {d.enrollment_status === "ENROLLED" && user?.permissions.includes("devices.release") && (
                      <button
                        onClick={() => {
                          setSelected(d);
                          setConfirmAction("release");
                        }}
                        className="px-2.5 py-1 rounded border border-red-300 text-red-700 hover:bg-red-50 font-medium"
                      >
                        Release
                      </button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {count > 25 && (
        <div className="flex justify-between items-center text-xs text-slate-600">
          <span>Page {page} · {count} total</span>
          <div className="flex gap-2">
            <button disabled={page <= 1} onClick={() => load(page - 1)} className="px-3 py-1 rounded border border-slate-300 bg-white disabled:opacity-40">Prev</button>
            <button disabled={page * 25 >= count} onClick={() => load(page + 1)} className="px-3 py-1 rounded border border-slate-300 bg-white disabled:opacity-40">Next</button>
          </div>
        </div>
      )}

      {selected && !confirmAction && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-900/40 p-4">
          <div className="bg-white rounded-lg border border-slate-200 shadow-xl w-full max-w-lg p-5 space-y-4">
            <div className="flex justify-between items-start">
              <div>
                <h3 className="text-base font-semibold text-slate-900">{selected.manufacturer} {selected.model}</h3>
                <p className="text-xs text-slate-500">{selected.registration_reference} · {selected.device_identifier}</p>
              </div>
              <button onClick={() => setSelected(null)} className="text-slate-400 hover:text-slate-700 text-sm">Close</button>
            </div>
            <div className="flex flex-wrap gap-2">
              <StatusBadge label={selected.connection_status} />
              <StatusBadge label={selected.enrollment_status} />
              <StatusBadge label={selected.restriction_status} />
            </div>
            <div className="text-xs space-y-1 bg-slate-50 p-3 rounded-lg border border-slate-200">
              <div><b>Customer:</b> {selected.customer_name ?? "-"} ({selected.customer_mobile_masked || "-"})</div>
              <div><b>Owner:</b> Retailer={selected.retailer_username ?? "Platform"} · Vendor={selected.vendor_username ?? "-"}</div>
              <div className="flex items-center gap-2">
                <b>IMEI:</b> <code>{revealedImei || selected.imei_masked || "-"}</code>
                {!revealedImei && selected.imei_masked && (
                  <button onClick={() => revealImei(selected)} className="text-indigo-600 font-medium hover:underline">Reveal (audited)</button>
                )}
              </div>
              <div>
                <b>GPS Location:</b>{" "}
                {selected.last_latitude !== null && selected.last_longitude !== null ? (
                  <>
                    <code>{selected.last_latitude.toFixed(5)}, {selected.last_longitude.toFixed(5)}</code>
                    {selected.last_location_accuracy !== null && ` (±${Math.round(selected.last_location_accuracy)}m)`}
                    {" · "}
                    <a
                      href={`https://maps.google.com/?q=${selected.last_latitude},${selected.last_longitude}`}
                      target="_blank"
                      rel="noreferrer"
                      className="text-indigo-600 font-medium hover:underline"
                    >
                      Open Map
                    </a>
                  </>
                ) : (
                  "Not reported yet"
                )}
              </div>
              <div>
                <b>Network:</b>{" "}
                {selected.network_type || "Unknown"}
                {selected.wifi_ssid ? ` · Wi-Fi: ${selected.wifi_ssid}` : ""}
                {selected.network_operator ? ` · ${selected.network_operator}` : ""}
                {selected.ip_address ? ` · IP: ${selected.ip_address}` : ""}
              </div>
              <div className="flex flex-wrap gap-2 pt-0.5">
                <StatusBadge label={selected.camera_disabled ? "CAMERA DISABLED" : "CAMERA ENABLED"} variant={selected.camera_disabled ? "danger" : "success"} />
                <StatusBadge label={selected.gps_forced_on ? "GPS LOCKED ON" : "GPS UNLOCKED"} variant={selected.gps_forced_on ? "info" : "neutral"} />
                <StatusBadge label={selected.network_restricted ? "NET SETTINGS LOCKED" : "NET SETTINGS OPEN"} variant={selected.network_restricted ? "warning" : "neutral"} />
                <StatusBadge
                  label={(selected.effective_frp_accounts?.length ?? 0) > 0 ? `FRP (${selected.effective_frp_accounts?.length})` : "FRP NOT SET"}
                  variant={(selected.effective_frp_accounts?.length ?? 0) > 0 ? "success" : "warning"}
                />
                {selected.app_version && <StatusBadge label={`APK v${selected.app_version}`} variant="neutral" />}
              </div>
              {selected.has_photo && (
                <div className="pt-1 flex items-center gap-2">
                  <button type="button" onClick={() => viewPhoto(selected)} className="text-indigo-600 font-medium hover:underline">
                    View Latest Camera Photo
                  </button>
                  {selected.last_photo_at && <span className="text-slate-400">({new Date(selected.last_photo_at).toLocaleString()})</span>}
                </div>
              )}
            </div>
            {photoData?.photo_b64 && (
              <div className="border border-slate-200 rounded-lg p-2 bg-slate-50 space-y-1">
                <div className="flex justify-between items-center text-[11px] text-slate-500">
                  <span>Captured {photoData.captured_at ? new Date(photoData.captured_at).toLocaleString() : ""}</span>
                  <button type="button" onClick={() => setPhotoData(null)} className="text-slate-600 hover:underline">Hide</button>
                </div>
                <img src={`data:image/jpeg;base64,${photoData.photo_b64}`} alt="Device capture" className="max-h-48 rounded mx-auto" />
              </div>
            )}
            <form onSubmit={saveLockDetails} className="space-y-2 border-t border-slate-200 pt-3">
              <div className="text-xs font-semibold text-slate-700">
                Lock-Screen EMI &amp; Dealer Details <span className="font-normal text-slate-400">(all optional)</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                <input
                  value={editLock.emi_amount}
                  onChange={(e) => setEditLock({ ...editLock, emi_amount: e.target.value })}
                  placeholder="EMI Amount"
                  className="rounded border border-slate-300 px-2.5 py-1.5 text-xs"
                />
                <input
                  type="date"
                  value={editLock.emi_due_date}
                  onChange={(e) => setEditLock({ ...editLock, emi_due_date: e.target.value })}
                  className="rounded border border-slate-300 px-2.5 py-1.5 text-xs"
                />
                <input
                  type="number"
                  min={0}
                  value={editLock.pending_emi_count}
                  onChange={(e) => setEditLock({ ...editLock, pending_emi_count: e.target.value })}
                  placeholder="Pending EMI"
                  className="rounded border border-slate-300 px-2.5 py-1.5 text-xs"
                />
                <input
                  value={editLock.dealer_company}
                  onChange={(e) => setEditLock({ ...editLock, dealer_company: e.target.value })}
                  placeholder="Dealer Company"
                  className="rounded border border-slate-300 px-2.5 py-1.5 text-xs"
                />
                <input
                  value={editLock.dealer_name}
                  onChange={(e) => setEditLock({ ...editLock, dealer_name: e.target.value })}
                  placeholder="Dealer Name"
                  className="rounded border border-slate-300 px-2.5 py-1.5 text-xs"
                />
                <input
                  value={editLock.dealer_mobile}
                  onChange={(e) => setEditLock({ ...editLock, dealer_mobile: e.target.value })}
                  placeholder="Dealer Mobile"
                  className="rounded border border-slate-300 px-2.5 py-1.5 text-xs"
                />
              </div>
              <div className="flex justify-end">
                <button
                  type="submit"
                  disabled={savingLock}
                  className="px-3 py-1 rounded bg-slate-800 text-white text-xs font-medium disabled:opacity-50"
                >
                  {savingLock ? "Saving..." : "Save Lock Details"}
                </button>
              </div>
            </form>
            {selected.enrollment_status === "ENROLLED" && (
              <div className="space-y-2 pt-2">
                <div className="flex flex-wrap gap-2">
                  <button onClick={() => setConfirmAction("lock")} className="px-3 py-1.5 rounded-lg bg-red-600 text-white text-xs font-medium">Lock Device</button>
                  <button onClick={() => setConfirmAction("unlock")} className="px-3 py-1.5 rounded-lg bg-green-600 text-white text-xs font-medium">Unlock Device</button>
                  <button onClick={() => runCommand(selected, "sync-command")} className="px-3 py-1.5 rounded-lg border border-slate-300 text-xs font-medium">Sync</button>
                  <button onClick={() => runCommand(selected, "locate")} className="px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-xs font-medium">Get GPS</button>
                  <button onClick={() => runCommand(selected, "capture-photo")} className="px-3 py-1.5 rounded-lg bg-sky-600 text-white text-xs font-medium">Capture Photo</button>
                  {user?.permissions.includes("devices.release") && (
                    <button onClick={() => setConfirmAction("release")} className="px-3 py-1.5 rounded-lg border border-red-300 text-red-700 text-xs font-medium">Release...</button>
                  )}
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() => runCommand(selected, "camera", { disable: !selected.camera_disabled })}
                    className="px-2.5 py-1 rounded border border-slate-300 text-xs font-medium hover:bg-slate-50"
                  >
                    {selected.camera_disabled ? "Enable Camera" : "Disable Camera"}
                  </button>
                  <button
                    onClick={() => runCommand(selected, "gps-policy", { lock: !selected.gps_forced_on })}
                    className="px-2.5 py-1 rounded border border-slate-300 text-xs font-medium hover:bg-slate-50"
                  >
                    {selected.gps_forced_on ? "Unlock GPS Setting" : "Force GPS On & Lock"}
                  </button>
                  <button
                    onClick={() => runCommand(selected, "network-policy", { restrict: !selected.network_restricted })}
                    className="px-2.5 py-1 rounded border border-slate-300 text-xs font-medium hover:bg-slate-50"
                  >
                    {selected.network_restricted ? "Unlock Network Settings" : "Lock Network Settings"}
                  </button>
                  <button
                    onClick={() => runCommand(selected, "update-agent")}
                    className="px-2.5 py-1 rounded bg-slate-900 text-white text-xs font-medium hover:bg-slate-800"
                  >
                    Push APK Update
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      <ConfirmModal
        open={Boolean(selected && confirmAction)}
        title={confirmAction === "release" ? "Release Device Permanently?" : `${confirmAction?.toUpperCase()} Device?`}
        message={
          confirmAction === "release"
            ? "Releasing removes Device Owner control. Historical ownership and the consumed entitlement are permanently preserved."
            : "This sends a cryptographically signed command. Offline devices remain pending until acknowledged."
        }
        confirmLabel={confirmAction?.toUpperCase()}
        danger={confirmAction === "lock" || confirmAction === "release"}
        requireText={confirmAction === "release" ? (selected?.registration_reference || selected?.device_identifier) : undefined}
        onCancel={() => setConfirmAction(null)}
        onConfirm={() => (selected && confirmAction ? runCommand(selected, confirmAction) : Promise.resolve())}
      />
    </div>
  );
}
