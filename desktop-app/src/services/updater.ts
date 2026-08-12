import { check, type Update } from "@tauri-apps/plugin-updater";
import { relaunch } from "@tauri-apps/plugin-process";
import { isTauriRuntime } from "../native";

export type { Update };

/** Consulta el servidor de updates configurado en tauri.conf.json. */
export async function checkForAppUpdate(): Promise<Update | null> {
  if (!isTauriRuntime()) return null;
  return check();
}

/** Descarga, instala y reinicia la app con la versión nueva. */
export async function installAppUpdate(update: Update): Promise<void> {
  await update.downloadAndInstall();
  await relaunch();
}
