const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export function getApiKey(): string {
  return localStorage.getItem("api_key") || "";
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  const key = getApiKey();
  if (key) headers["X-API-Key"] = key;
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

export function setApiKey(key: string) {
  localStorage.setItem("api_key", key);
}

export { API_BASE };
