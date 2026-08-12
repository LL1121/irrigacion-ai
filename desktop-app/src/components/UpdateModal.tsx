import { useState } from "react";
import { Download, LoaderCircle, Sparkles, X } from "lucide-react";
import type { Update } from "@tauri-apps/plugin-updater";
import { installAppUpdate } from "../services/updater";

type UpdateModalProps = {
  update: Update;
  onDismiss: () => void;
};

export function UpdateModal({ update, onDismiss }: UpdateModalProps) {
  const [installing, setInstalling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleInstall() {
    setInstalling(true);
    setError(null);
    try {
      await installAppUpdate(update);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "No se pudo instalar la actualización.",
      );
      setInstalling(false);
    }
  }

  return (
    <>
      <div className="fixed inset-0 z-[80] bg-black/35 backdrop-blur-sm" />
      <div className="fixed inset-x-4 top-[18vh] z-[90] mx-auto w-full max-w-md rounded-3xl border border-border bg-background p-5 shadow-2xl sm:inset-x-auto">
        <div className="mb-4 flex items-start gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-primary/15">
            <Sparkles size={20} className="text-primary" />
          </div>
          <div className="min-w-0 flex-1">
            <h2 className="text-base font-semibold text-foreground">
              Nueva versión disponible
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Hay una nueva versión de Irrigación Bot ({update.version}). ¿Querés
              actualizar ahora?
            </p>
          </div>
          <button
            type="button"
            onClick={onDismiss}
            disabled={installing}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-40"
          >
            <X size={16} />
          </button>
        </div>

        {update.body && (
          <div className="mb-4 max-h-32 overflow-y-auto rounded-2xl border border-border bg-muted/40 px-3 py-2 text-xs leading-relaxed text-muted-foreground">
            {update.body}
          </div>
        )}

        {error && (
          <p className="mb-3 rounded-xl border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
            {error}
          </p>
        )}

        <div className="flex flex-wrap justify-end gap-2">
          <button
            type="button"
            onClick={onDismiss}
            disabled={installing}
            className="rounded-xl border border-border px-4 py-2 text-sm text-muted-foreground hover:bg-muted disabled:opacity-40"
          >
            Más tarde
          </button>
          <button
            type="button"
            onClick={() => void handleInstall()}
            disabled={installing}
            className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-40"
          >
            {installing ? (
              <>
                <LoaderCircle size={15} className="animate-spin" />
                Actualizando…
              </>
            ) : (
              <>
                <Download size={15} />
                Actualizar ahora
              </>
            )}
          </button>
        </div>
      </div>
    </>
  );
}
