import React, { useState } from "react";
import { NavLink } from "react-router-dom";
import {
  Activity,
  KeyRound,
  LayoutDashboard,
  LogOut,
  Menu,
  PlusCircle,
  ShieldCheck,
  Smartphone,
  Store,
  Terminal,
  Users,
  X,
} from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { StatusBadge } from "./UI";

interface NavItem {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  roles: Array<"SUPERUSER" | "RETAILER" | "VENDOR">;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, roles: ["SUPERUSER", "RETAILER", "VENDOR"] },
  { to: "/retailers", label: "Retailers", icon: Store, roles: ["SUPERUSER"] },
  { to: "/vendors", label: "Vendors", icon: Users, roles: ["SUPERUSER", "RETAILER"] },
  { to: "/entitlements", label: "Entitlements", icon: KeyRound, roles: ["SUPERUSER", "RETAILER", "VENDOR"] },
  { to: "/customers", label: "Customers", icon: Users, roles: ["SUPERUSER", "RETAILER", "VENDOR"] },
  { to: "/devices", label: "Devices", icon: Smartphone, roles: ["SUPERUSER", "RETAILER", "VENDOR"] },
  { to: "/add-device", label: "Add Device", icon: PlusCircle, roles: ["SUPERUSER", "RETAILER", "VENDOR"] },
  { to: "/commands", label: "Commands", icon: Terminal, roles: ["SUPERUSER", "RETAILER", "VENDOR"] },
  { to: "/audit", label: "Audit Log", icon: Activity, roles: ["SUPERUSER", "RETAILER", "VENDOR"] },
  { to: "/security", label: "Security", icon: ShieldCheck, roles: ["SUPERUSER"] },
];

export function Layout({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const role = user?.account_type ?? "VENDOR";
  const items = NAV_ITEMS.filter((i) => i.roles.includes(role));

  const navList = (
    <nav className="space-y-1">
      {items.map((item) => {
        const Icon = item.icon;
        return (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            onClick={() => setMobileOpen(false)}
            className={({ isActive }) =>
              `flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition ${
                isActive
                  ? "bg-indigo-50 text-indigo-700"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
              }`
            }
          >
            <Icon className="w-4 h-4 shrink-0" />
            <span>{item.label}</span>
          </NavLink>
        );
      })}
    </nav>
  );

  return (
    <div className="min-h-screen flex bg-slate-50">
      <aside className="hidden lg:flex lg:flex-col lg:w-56 bg-white border-r border-slate-200 p-4 shrink-0">
        <div className="px-2 pb-5 flex items-center gap-2">
          <ShieldCheck className="w-5 h-5 text-indigo-600" />
          <span className="font-semibold text-base text-slate-900">AK DeviceLock</span>
        </div>
        {navList}
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden flex">
          <div className="w-64 bg-white h-full border-r border-slate-200 p-4 space-y-4">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-base">AK DeviceLock</span>
              <button onClick={() => setMobileOpen(false)} className="p-1 text-slate-500">
                <X className="w-5 h-5" />
              </button>
            </div>
            {navList}
          </div>
          <div className="flex-1 bg-slate-900/30" onClick={() => setMobileOpen(false)} />
        </div>
      )}

      <div className="flex-1 flex flex-col min-w-0">
        <header className="bg-white border-b border-slate-200 px-4 sm:px-6 py-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setMobileOpen(true)}
              className="lg:hidden p-1.5 rounded-lg border border-slate-200 text-slate-600"
              aria-label="Open menu"
            >
              <Menu className="w-5 h-5" />
            </button>
            <div className="flex items-center gap-2">
              <span className="font-medium text-slate-900">{user?.username}</span>
              <StatusBadge label={role} variant="info" />
            </div>
          </div>
          <button
            onClick={() => logout()}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 text-xs font-medium text-slate-700 hover:bg-slate-50"
          >
            <LogOut className="w-3.5 h-3.5" />
            Logout
          </button>
        </header>
        <main className="flex-1 p-4 sm:p-6 max-w-7xl w-full mx-auto">{children}</main>
      </div>
    </div>
  );
}
