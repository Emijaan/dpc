import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import { Layout } from "./components/Layout";
import { ActivityPage } from "./pages/ActivityPage";
import { AddDevicePage } from "./pages/AddDevicePage";
import { CustomersPage } from "./pages/CustomersPage";
import { DashboardPage } from "./pages/DashboardPage";
import { DevicesPage } from "./pages/DevicesPage";
import { EntitlementsPage } from "./pages/EntitlementsPage";
import { LoginPage } from "./pages/LoginPage";
import { SecurityPage } from "./pages/SecurityPage";
import { TenantsPage } from "./pages/TenantsPage";

function ProtectedRoutes() {
  const { user, loading } = useAuth();
  if (loading) {
    return <div className="min-h-screen flex items-center justify-center text-slate-500">Loading...</div>;
  }
  if (!user) return <LoginPage />;
  const role = user.account_type ?? "VENDOR";

  return (
    <Layout>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        {role === "SUPERUSER" && <Route path="/retailers" element={<TenantsPage mode="retailers" />} />}
        {(role === "SUPERUSER" || role === "RETAILER") && <Route path="/vendors" element={<TenantsPage mode="vendors" />} />}
        <Route path="/entitlements" element={<EntitlementsPage />} />
        <Route path="/customers" element={<CustomersPage />} />
        <Route path="/devices" element={<DevicesPage />} />
        <Route path="/add-device" element={<AddDevicePage />} />
        <Route path="/commands" element={<ActivityPage mode="commands" />} />
        <Route path="/audit" element={<ActivityPage mode="audit" />} />
        {role === "SUPERUSER" && <Route path="/security" element={<SecurityPage />} />}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}

export default function App() {
  return (
    <BrowserRouter basename="/app">
      <AuthProvider>
        <ProtectedRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}
