import { useEffect, useState } from "react";
import { api, downloadAuthorizedFile } from "../api/client";
import { StatusBadge } from "../components/UI";

interface RegResponse {
  registration_reference: string;
  device: { id: string };
  enrollment_session: { id: string; expires_at: string; enrollment_method: string };
  enrollment_token: string;
}

export function AddDevicePage() {
  const [customerName, setCustomerName] = useState("");
  const [customerMobile, setCustomerMobile] = useState("");
  const [customerEmail, setCustomerEmail] = useState("");
  const [brand, setBrand] = useState("");
  const [model, setModel] = useState("");
  const [imei, setImei] = useState("");
  const [androidVersion, setAndroidVersion] = useState("14");
  const [emiAmount, setEmiAmount] = useState("");
  const [emiDueDate, setEmiDueDate] = useState("");
  const [pendingEmiCount, setPendingEmiCount] = useState("");
  const [dealerName, setDealerName] = useState("");
  const [dealerMobile, setDealerMobile] = useState("");
  const [dealerCompany, setDealerCompany] = useState("");
  const [method, setMethod] = useState<"QR_9_15" | "ADB_16">("QR_9_15");
  const [reg, setReg] = useState<RegResponse | null>(null);
  const [testDpcSvg, setTestDpcSvg] = useState("");
  const [akdlSvg, setAkdlSvg] = useState("");
  const [liveStatus, setLiveStatus] = useState("PENDING");
  const [adbPrereqs, setAdbPrereqs] = useState(false);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  function onVersionChange(v: string) {
    setAndroidVersion(v);
    const major = parseInt(v.split(".")[0], 10);
    if (!Number.isNaN(major) && major >= 16) setMethod("ADB_16");
    else setMethod("QR_9_15");
  }

  function resetForm() {
    setCustomerName("");
    setCustomerMobile("");
    setCustomerEmail("");
    setBrand("");
    setModel("");
    setImei("");
    setAndroidVersion("14");
    setEmiAmount("");
    setEmiDueDate("");
    setPendingEmiCount("");
    setDealerName("");
    setDealerMobile("");
    setDealerCompany("");
    setMethod("QR_9_15");
    setReg(null);
    setTestDpcSvg("");
    setAkdlSvg("");
    setLiveStatus("PENDING");
    setAdbPrereqs(false);
    setErr("");
  }

  async function createPending(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    setBusy(true);
    setTestDpcSvg("");
    setAkdlSvg("");
    setLiveStatus("PENDING");
    try {
      const r = await api<RegResponse>("/api/v1/registrations/", {
        method: "POST",
        body: JSON.stringify({
          customer_name: customerName.trim(),
          customer_mobile: customerMobile.trim(),
          customer_email: customerEmail.trim(),
          brand: brand.trim(),
          model: model.trim(),
          imei: imei.trim(),
          android_version: androidVersion.trim(),
          emi_amount: emiAmount.trim(),
          emi_due_date: emiDueDate.trim(),
          pending_emi_count: pendingEmiCount.trim(),
          dealer_name: dealerName.trim(),
          dealer_mobile: dealerMobile.trim(),
          dealer_company: dealerCompany.trim(),
          enrollment_method: method,
        }),
      });
      setReg(r);
      if (method === "QR_9_15") {
        const major = parseInt(androidVersion.split(".")[0], 10);
        if (!Number.isNaN(major) && major <= 11) {
          const qDirect = await api<{ svg: string }>(`/api/v1/enrollment/${r.enrollment_session.id}/qr/?step=akdl&format=json`);
          setAkdlSvg(qDirect.svg);
        } else {
          const q1 = await api<{ svg: string }>(`/api/v1/enrollment/${r.enrollment_session.id}/qr/?step=testdpc&format=json`);
          setTestDpcSvg(q1.svg);
        }
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Registration failed");
    } finally {
      setBusy(false);
    }
  }

  async function generateAkQr() {
    if (!reg) return;
    setErr("");
    try {
      await api(`/api/v1/enrollment/${reg.enrollment_session.id}/complete/`, {
        method: "POST",
        body: JSON.stringify({ step: "test_dpc" }),
      });
      const q2 = await api<{ svg: string }>(`/api/v1/enrollment/${reg.enrollment_session.id}/qr/?step=akdl&format=json`);
      setAkdlSvg(q2.svg);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "QR generation failed");
    }
  }

  useEffect(() => {
    if (!reg || liveStatus === "USED") return;
    const timer = setInterval(async () => {
      try {
        const s = await api<{ status: string }>(`/api/v1/enrollment/${reg.enrollment_session.id}/status/`);
        setLiveStatus(s.status);
      } catch {
        // Ignore poll error
      }
    }, 5000);
    return () => clearInterval(timer);
  }, [reg, liveStatus]);

  return (
    <div className="max-w-3xl space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Add New Device</h1>
        <p className="text-xs text-slate-500">All fields are optional. No entitlement is consumed until the device finishes enrollment.</p>
      </div>

      {err && <div className="bg-red-50 border border-red-200 text-red-700 p-3 rounded-lg text-xs">{err}</div>}

      <form onSubmit={createPending} className="bg-white border border-slate-200 rounded-lg p-5 space-y-5">
        <div className="space-y-3">
          <h2 className="text-sm font-semibold text-slate-800">Customer Details (Optional)</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-600 mb-1">Customer Full Name</label>
              <input value={customerName} onChange={(e) => setCustomerName(e.target.value)} className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-xs text-slate-600 mb-1">Mobile Number</label>
              <input value={customerMobile} onChange={(e) => setCustomerMobile(e.target.value)} className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            </div>
            <div className="sm:col-span-2">
              <label className="block text-xs text-slate-600 mb-1">Email Address</label>
              <input type="email" value={customerEmail} onChange={(e) => setCustomerEmail(e.target.value)} className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            </div>
          </div>
        </div>

        <div className="border-t border-slate-200 pt-4 space-y-3">
          <h2 className="text-sm font-semibold text-slate-800">Device Details (Optional)</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-600 mb-1">Mobile Brand</label>
              <input value={brand} onChange={(e) => setBrand(e.target.value)} placeholder="Samsung / vivo" className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-xs text-slate-600 mb-1">Mobile Model</label>
              <input value={model} onChange={(e) => setModel(e.target.value)} placeholder="A15 / 1902" className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-xs text-slate-600 mb-1">IMEI Number (15 digits)</label>
              <input value={imei} onChange={(e) => setImei(e.target.value)} placeholder="490154203237518" className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-xs text-slate-600 mb-1">Android Version</label>
              <select value={androidVersion} onChange={(e) => onVersionChange(e.target.value)} className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm">
                <option value="9">Android 9</option>
                <option value="10">Android 10</option>
                <option value="11">Android 11</option>
                <option value="12">Android 12</option>
                <option value="13">Android 13</option>
                <option value="14">Android 14</option>
                <option value="15">Android 15</option>
                <option value="16">Android 16</option>
              </select>
            </div>
          </div>
          <div className="bg-indigo-50 border border-indigo-200 rounded-lg p-3 text-xs text-indigo-900">
            Selected enrollment method: <b>{method === "ADB_16" ? "Android 16 USB/ADB BAT Provisioning" : "Android 9–15 Guided QR Provisioning"}</b>
          </div>

          <div className="border-t border-slate-200 pt-4 space-y-3">
            <h2 className="text-sm font-semibold text-slate-800">
              EMI &amp; Dealer / Vendor Lock-Screen Details <span className="text-xs font-normal text-slate-500">(every field is optional)</span>
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">EMI Amount (optional)</label>
                <input
                  value={emiAmount}
                  onChange={(e) => setEmiAmount(e.target.value)}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  placeholder="e.g. ₹2,500"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">EMI Due Date (optional)</label>
                <input
                  type="date"
                  value={emiDueDate}
                  onChange={(e) => setEmiDueDate(e.target.value)}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Total Pending EMI (optional)</label>
                <input
                  type="number"
                  min={0}
                  value={pendingEmiCount}
                  onChange={(e) => setPendingEmiCount(e.target.value)}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  placeholder="e.g. 6"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Dealer / Vendor Company (optional)</label>
                <input
                  value={dealerCompany}
                  onChange={(e) => setDealerCompany(e.target.value)}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  placeholder="e.g. AK Mobiles Pvt Ltd"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Dealer / Vendor Name (optional)</label>
                <input
                  value={dealerName}
                  onChange={(e) => setDealerName(e.target.value)}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  placeholder="e.g. Rahul Sharma"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Dealer / Vendor Mobile No (optional)</label>
                <input
                  value={dealerMobile}
                  onChange={(e) => setDealerMobile(e.target.value)}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  placeholder="e.g. +91 9876543210"
                />
              </div>
            </div>
          </div>
        </div>

        <div className="flex items-center justify-between pt-1">
          {reg ? (
            <button type="button" onClick={resetForm} className="px-4 py-2 rounded-lg border border-slate-300 text-sm">
              Reset Form
            </button>
          ) : (
            <span className="text-xs text-slate-500">One entitlement is consumed only after the device completes enrollment.</span>
          )}
          <button type="submit" disabled={busy} className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium disabled:opacity-50">
            {busy ? "Creating..." : "Create Registration & Generate Enrollment"}
          </button>
        </div>
      </form>

      {reg && (
        <div className="bg-white border border-slate-200 rounded-lg p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold">Enroll Device ({reg.registration_reference})</h2>
              <p className="text-xs text-slate-500">Expires at {new Date(reg.enrollment_session.expires_at).toLocaleTimeString()}</p>
            </div>
            <StatusBadge label={liveStatus === "USED" ? "REGISTERED" : liveStatus} />
          </div>

          {method === "QR_9_15" ? (
            <div className="space-y-4">
              <div className="bg-indigo-50 border border-indigo-200 rounded-lg p-3 text-xs space-y-1">
                <div className="font-semibold text-indigo-900">Session Enrollment Key (single-use, binds device to {reg.registration_reference}):</div>
                <div className="flex items-center gap-2 flex-wrap">
                  <code className="bg-white px-2 py-1 rounded border border-indigo-200 text-indigo-900 select-all">{reg.enrollment_token}</code>
                  <button
                    type="button"
                    onClick={() => navigator.clipboard?.writeText(reg.enrollment_token)}
                    className="px-2.5 py-1 rounded bg-indigo-600 text-white font-medium"
                  >
                    Copy Key
                  </button>
                </div>
                <div className="text-indigo-800">If installing via Test DPC transfer or manual APK, paste this Session Key into AK DeviceLock on the phone before tapping Activate.</div>
              </div>

              {testDpcSvg && (
                <div className="border border-slate-200 rounded-lg p-4 space-y-2">
                  <div className="text-xs font-semibold text-slate-800">Step A — Test DPC QR (Android 12–15 setup bridge)</div>
                  <p className="text-xs text-slate-600">Factory-reset device, tap Welcome screen 6×, scan Test DPC QR, choose Work-Only, then disable Play Protect scan.</p>
                  <div className="bg-white inline-block p-2 border border-slate-200 rounded" dangerouslySetInnerHTML={{ __html: testDpcSvg }} />
                </div>
              )}

              <div className="border border-slate-200 rounded-lg p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="text-xs font-semibold text-slate-800">
                    {testDpcSvg ? "Step B — AK DeviceLock Direct QR" : "AK DeviceLock 1-Step Direct QR (Android 9–11)"}
                  </div>
                  <button type="button" onClick={generateAkQr} className="px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-xs font-medium">
                    {akdlSvg ? "Refresh AK DeviceLock QR" : "Generate AK DeviceLock QR"}
                  </button>
                </div>
                <p className="text-xs text-slate-600">
                  Factory-reset device, tap Welcome screen 6×, and scan this QR. It embeds the single-use Session Key automatically.
                </p>
                {akdlSvg && <div className="bg-white inline-block p-2 border border-slate-200 rounded" dangerouslySetInnerHTML={{ __html: akdlSvg }} />}
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-xs text-amber-900">
                <b>Android 16 Prerequisites:</b> Device must be factory-fresh with 0 Google/Samsung accounts, Samsung Auto Blocker OFF, Developer Options &amp; USB Debugging ON.
              </div>
              <label className="flex items-center gap-2 text-xs text-slate-700">
                <input type="checkbox" checked={adbPrereqs} onChange={(e) => setAdbPrereqs(e.target.checked)} />
                I confirm all Android 16 Device Owner prerequisites are met
              </label>
              <button
                type="button"
                disabled={!adbPrereqs}
                onClick={() => downloadAuthorizedFile(`/api/v1/enrollment/${reg.enrollment_session.id}/bat/`, `provision_${reg.registration_reference}.bat`)}
                className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium disabled:opacity-40"
              >
                Download Session .BAT File
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
