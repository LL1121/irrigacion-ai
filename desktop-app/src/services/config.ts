const STORAGE_KEY = "irrigacion.apiBaseUrl";

/**
 * Default: IP Tailscale del servidor (acceso remoto fuera de la LAN).
 * En oficina podés cambiar a LAN desde Configuración.
 */
export const DEFAULT_API_BASE = "http://100.68.57.77:8000";

/** IP LAN estática del servidor (red local de oficina). */
export const LAN_API_BASE = "http://172.30.12.101:8000";

function normalizeBase(url: string): string {
  return url.trim().replace(/\/$/, "");
}

export function getApiBaseUrl(): string {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored && stored.trim()) {
    const cleaned = normalizeBase(stored);
    if (cleaned === "http://127.0.0.1:8000" || cleaned === "http://localhost:8000") {
      return DEFAULT_API_BASE;
    }
    return cleaned;
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
