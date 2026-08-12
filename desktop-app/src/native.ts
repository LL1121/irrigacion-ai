import {
  isPermissionGranted,
  requestPermission,
  sendNotification,
} from "@tauri-apps/plugin-notification";
import {
  disable as disableAutostart,
  enable as enableAutostart,
  isEnabled as isAutostartEnabled,
} from "@tauri-apps/plugin-autostart";

/**
 * Distingue la app de escritorio real (Tauri) del `npm run dev` en el
 * navegador, donde estos plugins nativos no existen.
 */
export function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export async function ensureNotificationPermission(): Promise<boolean> {
  if (!isTauriRuntime()) return false;
  try {
    let granted = await isPermissionGranted();
    if (!granted) {
      granted = (await requestPermission()) === "granted";
    }
    return granted;
  } catch {
    return false;
  }
}

export function notifyDesktop(title: string, body: string): void {
  if (!isTauriRuntime()) return;
  try {
    void sendNotification({ title, body });
  } catch {
    // El SO puede negar el permiso o no soportar notificaciones; no es crítico.
  }
}

export async function getAutostartEnabled(): Promise<boolean> {
  if (!isTauriRuntime()) return false;
  try {
    return await isAutostartEnabled();
  } catch {
    return false;
  }
}

export async function setAutostartEnabled(enabled: boolean): Promise<void> {
  if (!isTauriRuntime()) return;
  try {
    if (enabled) await enableAutostart();
    else await disableAutostart();
  } catch {
    // Puede fallar en plataformas sin soporte para autostart.
  }
}
