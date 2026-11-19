import React, { useState } from "react";

type BadgeVariant = "success" | "warning" | "danger" | "neutral" | "info";

const BADGE_CLASSES: Record<BadgeVariant, string> = {
  success: "bg-green-50 text-green-700 border-green-200",
  warning: "bg-amber-50 text-amber-800 border-amber-200",
  danger: "bg-red-50 text-red-700 border-red-200",
  neutral: "bg-slate-100 text-slate-600 border-slate-200",
  info: "bg-indigo-50 text-indigo-700 border-indigo-200",
};

export function inferVariant(value: string): BadgeVariant {
  const v = value.toUpperCase();
  if (["ONLINE", "ACTIVE", "ENROLLED", "EXECUTED", "COMPLETED", "NONE", "UNLOCKED"].includes(v)) {
    return "success";
  }
  if (["PENDING", "LOCK_PENDING", "UNLOCK_PENDING", "RELEASE_PENDING", "DELIVERED", "ROTATED"].includes(v)) {
    return "warning";
  }
  if (["LOCKED", "FAILED", "EXPIRED", "REVOKED", "INACTIVE", "DISABLED"].includes(v)) {
    return "danger";
  }
  return "neutral";
}

export function StatusBadge({ label, variant }: { label: string; variant?: BadgeVariant }) {
  const cls = BADGE_CLASSES[variant ?? inferVariant(label)];
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${cls}`}>
      {label}
    </span>
  );
}

export function StatRow({ items }: { items: Array<{ label: string; value: string | number }> }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 bg-white border border-slate-200 rounded-lg divide-y sm:divide-y-0 sm:divide-x divide-slate-200">
      {items.map((item) => (
        <div key={item.label} className="p-4">
          <div className="text-xs text-slate-500 font-medium">{item.label}</div>
          <div className="text-xl font-semibold text-slate-900 mt-1">{item.value}</div>
        </div>
      ))}
    </div>
  );
}

export function ConfirmModal({
  open,
  title,
  message,
  confirmLabel = "Confirm",
  danger = false,
  requireText,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  danger?: boolean;
  requireText?: string;
  onCancel: () => void;
  onConfirm: (reason?: string) => Promise<void> | void;
}) {
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);

  if (!open) return null;
  const blocked = Boolean(requireText && typed.trim() !== requireText);

  async function handleConfirm() {
    setBusy(true);
    try {
      await onConfirm();
      setTyped("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
      <div className="bg-white rounded-lg border border-slate-200 shadow-xl w-full max-w-md p-5 space-y-4">
        <h3 className="text-base font-semibold text-slate-900">{title}</h3>
        <p className="text-sm text-slate-600">{message}</p>
        {requireText && (
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">
              Type <code className="bg-slate-100 px-1 rounded">{requireText}</code> to confirm
            </label>
            <input
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              placeholder={requireText}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={() => {
              setTyped("");
              onCancel();
            }}
            className="px-3.5 py-2 rounded-lg border border-slate-300 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={blocked || busy}
            onClick={handleConfirm}
            className={`px-3.5 py-2 rounded-lg text-sm font-medium text-white disabled:opacity-50 ${
              danger ? "bg-red-600 hover:bg-red-700" : "bg-indigo-600 hover:bg-indigo-700"
            }`}
          >
            {busy ? "Working..." : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
