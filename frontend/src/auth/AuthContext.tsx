import React, { createContext, useContext, useEffect, useState } from "react";
import { api, clearTokens, getTokens, setTokens } from "../api/client";
import type { AuthUser } from "../types";

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const { access } = getTokens();
    if (!access) {
      setLoading(false);
      return;
    }
    api<AuthUser>("/api/v1/auth/me/")
      .then(setUser)
      .catch(() => {
        clearTokens();
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, []);

  async function login(username: string, password: string) {
    const data = await api<{ access: string; refresh: string; user: AuthUser }>("/api/v1/auth/login/", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    setTokens(data.access, data.refresh);
    setUser(data.user);
  }

  async function logout() {
    const { refresh } = getTokens();
    try {
      if (refresh) {
        await api("/api/v1/auth/logout/", {
          method: "POST",
          body: JSON.stringify({ refresh }),
        });
      }
    } catch {
      // Ignore network errors during logout
    }
    clearTokens();
    setUser(null);
  }

  return <AuthContext.Provider value={{ user, loading, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be inside AuthProvider");
  return ctx;
}
