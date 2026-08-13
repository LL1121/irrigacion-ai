import { useMemo, useState } from "react";
import {
  LogIn,
  LogOut,
  MessageSquare,
  MessageSquarePlus,
  Search,
  Trash2,
  Waves,
  X,
} from "lucide-react";
import type { AuthUser, SessionSummary } from "../services/api";
import { getApiBaseUrl } from "../services/config";

type SidebarProps = {
  sessions: SessionSummary[];
  activeSessionId: string;
  apiOnline: boolean;
  open: boolean;
  authUser: AuthUser | null;
  authBusy?: boolean;
  onClose: () => void;
  onNewChat: () => void;
  onSelectSession: (sessionId: string) => void;
  onDeleteSession: (sessionId: string) => void;
  onGoogleLogin: () => void;
  onLogout: () => void;
};

function preview(text: string | null): string {
  if (!text) return "Sin mensajes";
  return text.length > 54 ? `${text.slice(0, 54)}…` : text;
}

function groupByDate(sessions: SessionSummary[]) {
  const now = Date.now();
  const today: SessionSummary[] = [];
  const yesterday: SessionSummary[] = [];
  const week: SessionSummary[] = [];
  const older: SessionSummary[] = [];

  for (const session of sessions) {
    if (!session.last_at) {
      older.push(session);
      continue;
    }
    const diffDays = (now - new Date(session.last_at).getTime()) / 86_400_000;
    if (diffDays < 1) today.push(session);
    else if (diffDays < 2) yesterday.push(session);
    else if (diffDays < 7) week.push(session);
    else older.push(session);
  }

  return { today, yesterday, week, older };
}

export function Sidebar({
  sessions,
  activeSessionId,
  apiOnline,
  open,
  authUser,
  authBusy = false,
  onClose,
  onNewChat,
  onSelectSession,
  onDeleteSession,
  onGoogleLogin,
  onLogout,
}: SidebarProps) {
  const [search, setSearch] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const filtered = useMemo(
    () =>
      sessions.filter((session) =>
        (session.last_message ?? "").toLowerCase().includes(search.toLowerCase()),
      ),
    [sessions, search],
  );

  const { today, yesterday, week, older } = groupByDate(filtered);

  function Section({ label, items }: { label: string; items: SessionSummary[] }) {
    if (items.length === 0) return null;
    return (
      <div className="mb-3">
        <p className="mb-1.5 px-3 text-[11px] font-medium uppercase tracking-wider text-muted-foreground/70">
          {label}
        </p>
        <div className="flex flex-col gap-0.5">
          {items.map((session) => {
            const active = session.session_id === activeSessionId;
            const deleting = deletingId === session.session_id;
            return (
              <div
                key={session.session_id}
                className={`group relative flex items-start gap-3 rounded-xl border px-3 py-2.5 text-left transition-all duration-150 ${
                  active
                    ? "border-primary/20 bg-primary/10"
                    : "border-transparent hover:bg-muted/60"
                }`}
              >
                <button
                  type="button"
                  onClick={() => onSelectSession(session.session_id)}
                  className="flex min-w-0 flex-1 items-start gap-3 text-left"
                >
                  <div
                    className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg transition-colors ${
                      active ? "bg-primary/20" : "bg-muted"
                    }`}
                  >
                    <MessageSquare
                      size={13}
                      className={active ? "text-primary" : "text-muted-foreground"}
                    />
                  </div>
                  <div className="min-w-0 flex-1 pr-6">
                    <p
                      className={`truncate text-sm leading-snug ${
                        active ? "text-primary" : "text-foreground"
                      }`}
                      style={{ fontWeight: active ? 500 : 400 }}
                    >
                      {preview(session.last_message)}
                    </p>
                  </div>
                </button>
                <button
                  type="button"
                  title="Borrar chat"
                  disabled={deleting}
                  onClick={(e) => {
                    e.stopPropagation();
                    if (
                      !window.confirm(
                        "¿Borrar esta conversación? No se puede deshacer.",
                      )
                    ) {
                      return;
                    }
                    setDeletingId(session.session_id);
                    void Promise.resolve(onDeleteSession(session.session_id)).finally(
                      () => setDeletingId(null),
                    );
                  }}
                  className={`absolute right-2 top-2.5 flex h-6 w-6 items-center justify-center rounded-lg text-muted-foreground transition-all hover:bg-destructive/10 hover:text-destructive disabled:opacity-40 ${
                    active || deleting
                      ? "opacity-100"
                      : "opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
                  }`}
                >
                  <Trash2 size={12} />
                </button>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  return (
    <>
      {open && (
        <div
          className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm md:hidden"
          onClick={onClose}
        />
      )}
      <aside
        className={`fixed inset-y-0 left-0 z-50 flex h-dvh w-72 shrink-0 transform flex-col border-r border-sidebar-border bg-sidebar transition-transform duration-300 ease-in-out md:static md:z-auto md:h-full md:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
      <div className="flex items-center gap-2.5 px-4 pt-5 pb-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-primary shadow-sm">
          <Waves size={16} className="text-primary-foreground" strokeWidth={2.2} />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm text-foreground" style={{ fontWeight: 600, lineHeight: 1.2 }}>
            Irrigación Bot
          </p>
          <p className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            Malargüe
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          title="Cerrar menú"
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl text-muted-foreground transition-all hover:bg-muted hover:text-foreground md:hidden"
        >
          <X size={16} />
        </button>
      </div>

      <div className="flex items-center gap-1.5 px-4 pb-3 text-[11px] text-muted-foreground">
        <span
          className={`h-1.5 w-1.5 rounded-full ${apiOnline ? "bg-primary" : "bg-destructive"}`}
        />
        {apiOnline ? "API conectada" : "API fuera de línea"}
      </div>

      <div className="px-3 pb-3">
        <button
          type="button"
          onClick={onNewChat}
          className="flex h-9 w-full items-center justify-start gap-2.5 rounded-xl border border-primary/20 bg-primary/8 px-3 text-sm text-primary transition-colors hover:bg-primary/15"
          style={{ fontWeight: 500 }}
        >
          <MessageSquarePlus size={15} />
          Nueva consulta
        </button>
      </div>

      <div className="px-3 pb-3">
        <div className="relative">
          <Search
            size={13}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
          />
          <input
            type="text"
            placeholder="Buscar conversaciones..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-xl border border-border bg-muted/60 py-2 pl-8 pr-8 text-sm text-foreground placeholder:text-muted-foreground/60 transition-all focus:outline-none focus:ring-1 focus:ring-ring"
          />
          {search && (
            <button
              type="button"
              onClick={() => setSearch("")}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              <X size={12} />
            </button>
          )}
        </div>
      </div>

      <div className="mx-3 mb-3 h-px bg-sidebar-border" />

      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-4">
        {filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center px-4 py-12 text-center">
            <MessageSquare size={28} className="mb-3 text-muted-foreground/40" />
            <p className="text-sm text-muted-foreground">
              {search ? "Sin resultados" : "Todavía no hay conversaciones guardadas"}
            </p>
          </div>
        ) : (
          <div className="pb-2">
            <Section label="Hoy" items={today} />
            <Section label="Ayer" items={yesterday} />
            <Section label="Esta semana" items={week} />
            <Section label="Anteriores" items={older} />
          </div>
        )}
      </div>

      <div className="border-t border-sidebar-border px-4 py-3">
        {authUser ? (
          <div className="mb-3 flex items-center gap-2.5">
            {authUser.picture ? (
              <img
                src={authUser.picture}
                alt=""
                className="h-8 w-8 rounded-full object-cover"
                referrerPolicy="no-referrer"
              />
            ) : (
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-muted text-xs font-medium text-foreground">
                {(authUser.name || authUser.email || "?").slice(0, 1).toUpperCase()}
              </div>
            )}
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-medium text-foreground">
                {authUser.name || authUser.email}
              </p>
              <p className="truncate text-[10px] text-muted-foreground">{authUser.email}</p>
            </div>
            <button
              type="button"
              title="Cerrar sesión"
              disabled={authBusy}
              onClick={onLogout}
              className="flex h-8 w-8 items-center justify-center rounded-xl text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-50"
            >
              <LogOut size={14} />
            </button>
          </div>
        ) : (
          <button
            type="button"
            disabled={authBusy || !apiOnline}
            onClick={onGoogleLogin}
            className="mb-3 flex h-9 w-full items-center justify-center gap-2 rounded-xl border border-border bg-background px-3 text-sm text-foreground transition-colors hover:bg-muted disabled:opacity-50"
            style={{ fontWeight: 500 }}
          >
            <LogIn size={14} />
            Iniciar sesión con Google
          </button>
        )}
        <p className="truncate font-mono text-[10px] text-muted-foreground/70">
          {getApiBaseUrl()}
        </p>
      </div>
      </aside>
    </>
  );
}
