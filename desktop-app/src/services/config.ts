import { isTauriRuntime } from "../native";

const STORAGE_KEY = "irrigacion.apiBaseUrl";

/**
 * Default para Tauri: IP Tailscale del servidor (acceso remoto fuera de la LAN).
 * En oficina podés cambiar a LAN desde Configuración.
 */
export const DEFAULT_API_BASE = "http://100.68.57.77:8000";

/** IP LAN estática del servidor (red local de oficina). */
export const LAN_API_BASE = "http://172.30.12.101:8000";

function normalizeBase(url: string): string {
  return url.trim().replace(/\/$/, "");
}

/** Vite/Tauri dev (`npm run dev` / `tauri dev`) — no es la PWA en producción. */
function isLocalDevServer(): boolean {
  if (typeof window === "undefined") return false;
  const port = window.location.port;
  return port === "1420" || port === "5173";
}

/**
 * Cuando la PWA se sirve desde FastAPI (mismo host:puerto que /api/*),
 * la API vive en el mismo origen — sin CORS ni URL manual en el celular.
 */
function sameOriginApiBase(): string | null {
  if (typeof window === "undefined") return null;
  if (isTauriRuntime() || isLocalDevServer()) return null;
  return window.location.origin;
}

export function isSameOriginDeployment(): boolean {
  const api = getApiBaseUrl();
  return sameOriginApiBase() === api;
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
  const origin = sameOriginApiBase();
  if (origin) {
    return origin;
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
