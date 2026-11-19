const ACCESS_KEY = "akdl_access";
const REFRESH_KEY = "akdl_refresh";

export function getTokens() {
  return {
    access: localStorage.getItem(ACCESS_KEY),
    refresh: localStorage.getItem(REFRESH_KEY),
  };
}

export function setTokens(access: string, refresh: string) {
  localStorage.setItem(ACCESS_KEY, access);
  localStorage.setItem(REFRESH_KEY, refresh);
}

export function clearTokens() {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

async function refreshAccess(): Promise<string | null> {
  const { refresh } = getTokens();
  if (!refresh) return null;
  const res = await fetch("/api/v1/auth/refresh/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh }),
  });
  if (!res.ok) {
    clearTokens();
    return null;
  }
  const data = await res.json();
  setTokens(data.access, data.refresh ?? refresh);
  return data.access;
}

export async function api<T = unknown>(
  path: string,
  init: RequestInit = {},
  retry = true
): Promise<T> {
  const { access } = getTokens();
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && init.body && typeof init.body === "string") {
    headers.set("Content-Type", "application/json");
  }
  if (access) headers.set("Authorization", `Bearer ${access}`);

  const res = await fetch(path, { ...init, headers });
  if (res.status === 401 && retry) {
    const newAccess = await refreshAccess();
    if (newAccess) {
      return api<T>(path, init, false);
    }
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let json: unknown = null;
  try {
    json = text ? JSON.parse(text) : null;
  } catch {
    json = text;
  }
  if (!res.ok) {
    const msg =
      (json && typeof json === "object" && ("error" in json || "detail" in json)
        ? String((json as Record<string, unknown>).error ?? (json as Record<string, unknown>).detail)
        : JSON.stringify(json)) || `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return json as T;
}

export async function downloadAuthorizedFile(path: string, filename: string) {
  const { access } = getTokens();
  const res = await fetch(path, {
    headers: access ? { Authorization: `Bearer ${access}` } : {},
  });
  if (!res.ok) {
    throw new Error(`Download failed (${res.status})`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
