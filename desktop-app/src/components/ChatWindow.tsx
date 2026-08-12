import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  ClipboardList,
  Download,
  Droplets,
  FileSearch,
  Gavel,
  LoaderCircle,
  MapPin,
  Menu,
  Moon,
  Paperclip,
  Send,
  Settings,
  ShieldCheck,
  Sparkles,
  Sun,
  X,
} from "lucide-react";
import type { ChatMessage, SpeedMode } from "../services/api";
import { useTheme } from "../theme";

type ChatWindowProps = {
  messages: ChatMessage[];
  loading: boolean;
  approving?: boolean;
  apiOnline: boolean;
  showTimestamps: boolean;
  speedMode: SpeedMode;
  onSpeedModeChange: (mode: SpeedMode) => void;
  onSend: (message: string) => Promise<void> | void;
  onApproveSkill?: (approved: boolean) => Promise<void> | void;
  onOpenSettings: () => void;
  onOpenUpload: () => void;
  onOpenSidebar: () => void;
};

const SPEED_MODES: { value: SpeedMode; emoji: string; label: string; title: string }[] = [
  {
    value: "fast",
    emoji: "⚡",
    label: "Rápido",
    title: "Rápido: 2 fragmentos de contexto — respuesta más veloz",
  },
  {
    value: "balanced",
    emoji: "⚖️",
    label: "Equilibrado",
    title: "Equilibrado: 5 fragmentos de contexto — velocidad y profundidad medias",
  },
  {
    value: "deep",
    emoji: "🎯",
    label: "Profundo",
    title: "Profundo (predeterminado): 10 fragmentos de contexto — máxima precisión",
  },
];

const SUGGESTED_PROMPTS = [
  {
    icon: Droplets,
    label: "Consultar caudales",
    prompt: "¿Cuál es el caudal habilitado para la toma que te voy a indicar?",
  },
  {
    icon: FileSearch,
    label: "Buscar resolución",
    prompt: "Necesito encontrar una resolución sobre una obra de toma específica.",
  },
  {
    icon: Gavel,
    label: "Explicar normativa",
    prompt: "Explicame de forma sencilla qué establece esta resolución o acta.",
  },
  {
    icon: MapPin,
    label: "Datos de una toma",
    prompt: "Contame qué información tenés registrada sobre esta toma de agua.",
  },
  {
    icon: ClipboardList,
    label: "Redactar informe",
    prompt: "Ayudame a redactar un informe técnico con los datos que ya indexamos.",
  },
  {
    icon: Paperclip,
    label: "Analizar un documento",
    prompt: "Adjunté un documento nuevo, ¿podés resumir lo más importante?",
  },
];

function isPendingApproval(msg: ChatMessage, isLast: boolean): boolean {
  return isLast && msg.status === "REQUIRES_APPROVAL" && msg.role !== "user";
}

function formatTime(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit" });
}

function exportConversation(messages: ChatMessage[]) {
  const lines = messages.map((msg) => {
    const time = formatTime(msg.created_at);
    const who = msg.role === "user" ? "Vos" : "Asistente";
    const prefix = time ? `[${time}] ${who}` : who;
    return `${prefix}: ${msg.message}`;
  });
  const blob = new Blob([lines.join("\n\n")], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const stamp = new Date().toISOString().slice(0, 16).replace(/[:T]/g, "-");
  const link = document.createElement("a");
  link.href = url;
  link.download = `conversacion-${stamp}.txt`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

function TypingIndicator({ label }: { label: string }) {
  return (
    <div className="mb-4 flex items-start gap-3">
      <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-2xl bg-primary/15">
        <Sparkles size={14} className="text-primary" />
      </div>
      <div className="flex items-center gap-2 rounded-3xl rounded-tl-sm border border-border bg-card px-4 py-3 text-sm text-muted-foreground shadow-sm">
        <LoaderCircle className="animate-spin" size={14} />
        {label}
      </div>
    </div>
  );
}

export function ChatWindow({
  messages,
  loading,
  approving = false,
  apiOnline,
  showTimestamps,
  speedMode,
  onSpeedModeChange,
  onSend,
  onApproveSkill,
  onOpenSettings,
  onOpenUpload,
  onOpenSidebar,
}: ChatWindowProps) {
  const { resolvedTheme, setTheme } = useTheme();
  const isDark = resolvedTheme === "dark";
  const [draft, setDraft] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const last = messages[messages.length - 1];
  const waitingApproval = Boolean(
    last && last.status === "REQUIRES_APPROVAL" && last.role !== "user",
  );
  const inputLocked = loading || approving || waitingApproval;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading, approving]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || inputLocked) return;
    setDraft("");
    await onSend(text);
  }

  return (
    <main className="relative flex min-w-0 flex-1 flex-col">
      <header className="flex shrink-0 items-center justify-between gap-2 border-b border-border bg-background/80 px-3 py-2.5 backdrop-blur-sm sm:px-6 sm:py-3">
        <div className="flex min-w-0 items-center gap-2 sm:gap-2.5">
          <button
            type="button"
            onClick={onOpenSidebar}
            title="Abrir menú"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-muted-foreground transition-all hover:bg-muted hover:text-foreground md:hidden"
          >
            <Menu size={18} />
          </button>
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-primary/15">
            <Sparkles size={15} className="text-primary" />
          </div>
          <div className="hidden min-w-0 sm:block">
            <p className="truncate text-sm text-foreground" style={{ fontWeight: 600, lineHeight: 1.2 }}>
              Consulta técnica
            </p>
            <p className="text-[11px] text-muted-foreground">
              {loading || approving
                ? "Analizando…"
                : apiOnline
                  ? "En línea"
                  : "Fuera de línea"}
            </p>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-0.5 rounded-xl border border-border bg-muted/40 p-0.5 sm:gap-1.5">
          {SPEED_MODES.map((mode) => (
            <button
              key={mode.value}
              type="button"
              title={mode.title}
              onClick={() => onSpeedModeChange(mode.value)}
              className={`rounded-lg px-2 py-1.5 text-[11px] font-medium transition-all sm:px-2.5 sm:py-1 ${
                speedMode === mode.value
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-muted-foreground hover:bg-background hover:text-foreground"
              }`}
            >
              <span aria-hidden="true">{mode.emoji}</span>
              <span className="hidden sm:inline"> {mode.label}</span>
            </button>
          ))}
        </div>

        <div className="flex shrink-0 items-center gap-0.5 sm:gap-1.5">
          <button
            type="button"
            onClick={() => exportConversation(messages)}
            disabled={messages.length === 0}
            title="Exportar conversación"
            className="hidden h-9 w-9 items-center justify-center rounded-xl text-muted-foreground transition-all hover:bg-muted hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40 sm:flex sm:h-8 sm:w-8"
          >
            <Download size={16} />
          </button>
          <button
            type="button"
            onClick={() => setTheme(isDark ? "light" : "dark")}
            title={isDark ? "Modo día" : "Modo noche"}
            className="flex h-9 w-9 items-center justify-center rounded-xl text-muted-foreground transition-all hover:bg-muted hover:text-foreground sm:h-8 sm:w-8"
          >
            {isDark ? <Sun size={16} /> : <Moon size={16} />}
          </button>
          <button
            type="button"
            onClick={onOpenSettings}
            title="Configuración"
            className="flex h-9 w-9 items-center justify-center rounded-xl text-muted-foreground transition-all hover:bg-muted hover:text-foreground sm:h-8 sm:w-8"
          >
            <Settings size={16} />
          </button>
        </div>
      </header>

      {messages.length === 0 && !loading ? (
        <div className="flex flex-1 flex-col items-center justify-center overflow-y-auto px-4 py-6 sm:px-6 sm:py-8">
          <div className="mb-5 flex h-14 w-14 items-center justify-center rounded-3xl bg-primary/15 shadow-sm sm:h-16 sm:w-16">
            <Sparkles size={26} className="text-primary" />
          </div>
          <h2 className="mb-1.5 text-center text-foreground" style={{ fontWeight: 600, fontSize: "1.15rem" }}>
            ¿En qué te puedo ayudar?
          </h2>
          <p className="mb-8 max-w-sm text-center text-sm text-muted-foreground">
            Subí actas, resoluciones o planos, y preguntá por caudales, tomas o
            resoluciones específicas.
          </p>

          <div className="grid w-full max-w-2xl grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {SUGGESTED_PROMPTS.map(({ icon: Icon, label, prompt }) => (
              <button
                key={label}
                type="button"
                onClick={() => void onSend(prompt)}
                className="group flex items-start gap-3 rounded-2xl border border-border bg-card p-4 text-left shadow-sm transition-all duration-150 active:scale-[0.98] hover:border-primary/25 hover:bg-accent"
              >
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-primary/10 transition-colors group-hover:bg-primary/20">
                  <Icon size={15} className="text-primary" />
                </div>
                <div>
                  <p className="text-sm leading-snug text-foreground" style={{ fontWeight: 500 }}>
                    {label}
                  </p>
                  <p className="mt-0.5 line-clamp-2 text-xs leading-snug text-muted-foreground">
                    {prompt}
                  </p>
                </div>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-3xl px-3 py-4 sm:px-4 sm:py-6">
            {messages.map((msg, index) => {
              const isUser = msg.role === "user";
              const isLast = index === messages.length - 1;
              const showCard = msg.status === "REQUIRES_APPROVAL" && !isUser;

              if (showCard) {
                return (
                  <div key={`${msg.role}-${index}-${msg.created_at ?? index}`} className="mb-4 flex items-start gap-3">
                    <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-2xl bg-primary/15">
                      <Sparkles size={14} className="text-primary" />
                    </div>
                    <div className="max-w-[88%] rounded-3xl rounded-tl-sm border border-primary/30 bg-card px-4 py-3 shadow-sm sm:max-w-[78%]">
                      <div className="mb-2 inline-flex items-center gap-1 rounded-md bg-primary/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-primary">
                        Autorización de skill
                      </div>
                      <p className="text-sm leading-relaxed text-foreground">
                        No tengo esta habilidad. Se encontró la skill{" "}
                        <span className="font-semibold text-primary">
                          '{msg.skill_name || "desconocida"}'
                        </span>
                        . ¿Autorizás a Gemini a auditarla y ejecutarla en el sandbox?
                      </p>
                      {msg.skill_description && (
                        <p className="mt-2 text-xs text-muted-foreground">{msg.skill_description}</p>
                      )}
                      {isPendingApproval(msg, isLast) && onApproveSkill && (
                        <div className="mt-3 flex flex-wrap gap-2">
                          <button
                            type="button"
                            disabled={approving}
                            onClick={() => void onApproveSkill(true)}
                            className="inline-flex items-center gap-1.5 rounded-xl bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground transition hover:opacity-90 disabled:opacity-40"
                          >
                            <ShieldCheck size={14} />
                            Autorizar
                          </button>
                          <button
                            type="button"
                            disabled={approving}
                            onClick={() => void onApproveSkill(false)}
                            className="inline-flex items-center gap-1.5 rounded-xl border border-border px-3 py-1.5 text-xs font-semibold text-muted-foreground transition hover:border-destructive/40 hover:text-destructive disabled:opacity-40"
                          >
                            <X size={14} />
                            Cancelar
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                );
              }

              const time = showTimestamps ? formatTime(msg.created_at) : null;

              if (isUser) {
                return (
                  <div key={`${msg.role}-${index}-${msg.created_at ?? index}`} className="mb-4 flex justify-end">
                    <div className="max-w-[85%] sm:max-w-[75%]">
                      <div className="rounded-3xl rounded-tr-sm bg-primary px-4 py-3 text-primary-foreground shadow-sm">
                        <p className="whitespace-pre-wrap text-sm leading-relaxed">{msg.message}</p>
                      </div>
                      {time && (
                        <p className="mt-1 pr-1 text-right text-[10px] text-muted-foreground">{time}</p>
                      )}
                    </div>
                  </div>
                );
              }

              return (
                <div key={`${msg.role}-${index}-${msg.created_at ?? index}`} className="mb-4 flex items-start gap-3">
                  <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-2xl bg-primary/15">
                    <Sparkles size={14} className="text-primary" />
                  </div>
                  <div className="max-w-[88%] sm:max-w-[78%]">
                    <div className="rounded-3xl rounded-tl-sm border border-border bg-card px-4 py-3 shadow-sm">
                      {msg.from_cache && (
                        <div className="mb-2 inline-flex items-center gap-1 rounded-md bg-primary/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-primary">
                          Caché semántico
                        </div>
                      )}
                      <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">
                        {msg.message}
                      </p>
                    </div>
                    {time && <p className="mt-1 pl-1 text-[10px] text-muted-foreground">{time}</p>}
                  </div>
                </div>
              );
            })}

            {(loading || approving) && (
              <TypingIndicator
                label={approving ? "Gemini audita y el sandbox ejecuta la skill…" : "Analizando contexto…"}
              />
            )}
            <div ref={bottomRef} />
          </div>
        </div>
      )}

      <form
        onSubmit={handleSubmit}
        className="shrink-0 px-3 pt-2 pb-[max(1rem,env(safe-area-inset-bottom))] sm:px-4 sm:pb-4"
      >
        {waitingApproval && (
          <p className="mb-2 px-1 text-xs text-muted-foreground">
            Autorizá o cancelá la skill pendiente para continuar el chat.
          </p>
        )}
        <div className="mx-auto flex max-w-3xl items-end gap-1.5 rounded-3xl border border-border bg-card px-2.5 py-2 shadow-sm transition-all duration-200 focus-within:border-primary/40 focus-within:shadow-md sm:gap-2 sm:px-3 sm:py-2.5">
          <button
            type="button"
            onClick={onOpenUpload}
            title="Indexar documentos"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-muted-foreground transition-all hover:bg-primary/10 hover:text-primary sm:h-8 sm:w-8"
          >
            <Paperclip size={17} />
          </button>

          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={1}
            placeholder={
              waitingApproval ? "Pendiente de autorización…" : "Escribí tu consulta técnica…"
            }
            disabled={inputLocked}
            className="max-h-40 min-h-9 flex-1 resize-none bg-transparent py-1 text-sm text-foreground outline-none placeholder:text-muted-foreground/60 disabled:opacity-50 sm:min-h-8"
            style={{ lineHeight: "1.5" }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void handleSubmit(e);
              }
            }}
          />

          <button
            type="submit"
            disabled={inputLocked || !draft.trim()}
            className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl transition-all duration-200 sm:h-8 sm:w-8 ${
              !inputLocked && draft.trim()
                ? "bg-primary text-primary-foreground shadow-sm hover:opacity-90"
                : "cursor-not-allowed bg-muted text-muted-foreground"
            }`}
          >
            <Send size={15} />
          </button>
        </div>

        <p className="mt-2 text-center text-[10px] text-muted-foreground/50">
          El asistente puede cometer errores. Verificá la información crítica.
        </p>
      </form>
    </main>
  );
}
