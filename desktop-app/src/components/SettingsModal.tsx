import { useEffect, useState, type FormEvent } from "react";
import { X } from "lucide-react";
import { getApiBaseUrl, setApiBaseUrl } from "../services/config";
import { healthCheck } from "../services/api";

type SettingsModalProps = {
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
};

export function SettingsModal({ open, onClose, onSaved }: SettingsModalProps) {
  const [url, setUrl] = useState(getApiBaseUrl);
  const [testing, setTesting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setUrl(getApiBaseUrl());
      setMessage(null);
    }
  }, [open]);

  if (!open) return null;

  async function handleSave(event: FormEvent) {
    event.preventDefault();
    setApiBaseUrl(url);
    setTesting(true);
    setMessage(null);
    try {
      const ok = await healthCheck();
      setMessage(
        ok
          ? "Guardado. API alcanzable."
          : "Guardado, pero no se pudo conectar. Revisá la URL / firewall.",
      );
      onSaved();
    } finally {
      setTesting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/70 p-4 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl border border-border bg-panel shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <div>
            <h3 className="text-sm font-semibold text-text">Configuración</h3>
            <p className="text-xs text-muted">URL del servidor de la oficina</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1.5 text-muted transition hover:bg-panel-2 hover:text-text"
          >
            <X size={16} />
          </button>
        </div>

        <form onSubmit={handleSave} className="space-y-4 p-5">
          <label className="block space-y-1.5">
            <span className="text-xs font-medium text-muted">API base URL</span>
            <input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="http://172.30.12.101:8000"
              className="w-full rounded-lg border border-border bg-panel-2 px-3 py-2 font-mono text-sm text-text outline-none focus:border-accent/50"
            />
          </label>
          <p className="text-[11px] leading-relaxed text-muted">
            Por defecto apunta al servidor de la oficina{" "}
            <span className="font-mono text-accent">http://172.30.12.101:8000</span>.
            Solo cambiá esto si el backend se mueve de host.
          </p>
          {message && (
            <p className="rounded-lg border border-border bg-panel-2 px-3 py-2 text-xs text-text">
              {message}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-border px-3 py-2 text-sm text-muted hover:text-text"
            >
              Cerrar
            </button>
            <button
              type="submit"
              disabled={testing || !url.trim()}
              className="rounded-lg bg-accent px-3 py-2 text-sm font-semibold text-ink hover:bg-accent-dim disabled:opacity-40"
            >
              {testing ? "Probando…" : "Guardar"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
