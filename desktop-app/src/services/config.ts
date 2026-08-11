const STORAGE_KEY = "irrigacion.apiBaseUrl";

/** Servidor estático de producción (oficina Irrigación). */
export const DEFAULT_API_BASE = "http://172.30.12.101:8000";

const LEGACY_LOCAL_DEFAULTS = new Set([
  "http://127.0.0.1:8000",
  "http://localhost:8000",
]);

function normalizeBase(url: string): string {
  return url.trim().replace(/\/$/, "");
}

export function getApiBaseUrl(): string {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored && stored.trim()) {
    const cleaned = normalizeBase(stored);
    // Si quedó un default local viejo en storage, usar el servidor de producción.
    if (!LEGACY_LOCAL_DEFAULTS.has(cleaned)) {
      return cleaned;
    }
  }
  const fromEnv = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim();
  if (fromEnv) {
    return normalizeBase(fromEnv);
  }
  return DEFAULT_API_BASE;
}

export function setApiBaseUrl(url: string): void {
  const cleaned = normalizeBase(url);
  if (!cleaned) {
    localStorage.removeItem(STORAGE_KEY);
    return;
  }
  localStorage.setItem(STORAGE_KEY, cleaned);
}
