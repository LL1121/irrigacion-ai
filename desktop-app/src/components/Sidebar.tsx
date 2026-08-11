import { FileUp, MessageSquarePlus, Settings, Waves } from "lucide-react";
import type { SessionSummary } from "../services/api";
import { getApiBaseUrl } from "../services/config";

type SidebarProps = {
  sessions: SessionSummary[];
  activeSessionId: string;
  apiOnline: boolean;
  onNewChat: () => void;
  onSelectSession: (sessionId: string) => void;
  onOpenUpload: () => void;
  onOpenSettings: () => void;
};

function preview(text: string | null): string {
  if (!text) return "Sin mensajes";
  return text.length > 54 ? `${text.slice(0, 54)}…` : text;
}

export function Sidebar({
  sessions,
  activeSessionId,
  apiOnline,
  onNewChat,
  onSelectSession,
  onOpenUpload,
  onOpenSettings,
}: SidebarProps) {
  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r border-border bg-panel/90 backdrop-blur">
      <div className="border-b border-border px-4 py-5">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent/15 text-accent">
            <Waves size={18} strokeWidth={2.2} />
          </div>
          <div className="min-w-0 flex-1">
            <h1 className="text-sm font-semibold tracking-wide text-text">
              Irrigación Bot
            </h1>
            <p className="text-[11px] uppercase tracking-[0.14em] text-muted">
              Malargüe
            </p>
          </div>
          <button
            type="button"
            onClick={onOpenSettings}
            title="Configuración del servidor"
            className="rounded-md p-1.5 text-muted transition hover:bg-panel-2 hover:text-accent"
          >
            <Settings size={16} />
          </button>
        </div>
        <div className="mt-3 flex items-center gap-2 text-[11px] text-muted">
          <span
            className={`h-1.5 w-1.5 rounded-full ${apiOnline ? "bg-accent" : "bg-danger"}`}
          />
          {apiOnline ? "API conectada" : "API fuera de línea"}
        </div>
        <div className="mt-1 truncate font-mono text-[10px] text-muted/80">
          {getApiBaseUrl()}
        </div>
      </div>

      <div className="flex gap-2 p-3">
        <button
          type="button"
          onClick={onNewChat}
          className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-semibold text-ink transition hover:bg-accent-dim"
        >
          <MessageSquarePlus size={16} />
          Nueva consulta
        </button>
        <button
          type="button"
          onClick={onOpenUpload}
          title="Subir documentos"
          className="rounded-lg border border-border bg-panel-2 px-3 py-2 text-muted transition hover:border-accent/40 hover:text-accent"
        >
          <FileUp size={16} />
        </button>
      </div>

      <div className="px-3 pb-2 text-[11px] font-medium uppercase tracking-[0.12em] text-muted">
        Historial
      </div>

      <div className="min-h-0 flex-1 space-y-1 overflow-y-auto px-2 pb-4">
        {sessions.length === 0 && (
          <p className="px-2 py-3 text-xs text-muted">
            Todavía no hay conversaciones guardadas.
          </p>
        )}
        {sessions.map((session) => {
          const active = session.session_id === activeSessionId;
          return (
            <button
              key={session.session_id}
              type="button"
              onClick={() => onSelectSession(session.session_id)}
              className={`w-full rounded-lg px-3 py-2.5 text-left transition ${
                active
                  ? "bg-accent/10 ring-1 ring-accent/30"
                  : "hover:bg-panel-2"
              }`}
            >
              <div className="truncate text-xs font-medium text-text">
                {preview(session.last_message)}
              </div>
              <div className="mt-1 font-mono text-[10px] text-muted">
                {session.session_id.slice(0, 8)}…
              </div>
            </button>
          );
        })}
      </div>
    </aside>
  );
}
