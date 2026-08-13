import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import {
  ClipboardList,
  Download,
  Droplets,
  FileSearch,
  Gavel,
  Globe,
  LoaderCircle,
  MapPin,
  Menu,
  Moon,
  Paperclip,
  Pencil,
  Send,
  Settings,
  ShieldCheck,
  Sparkles,
  Square,
  Sun,
  X,
} from "lucide-react";
import type { ChatAttachment, ChatMessage } from "../services/api";
import { useTypewriter } from "../hooks/useTypewriter";
import { useTheme } from "../theme";
import { AttachmentCard, FileViewerModal } from "./FileViewerModal";
import { cleanMessageText, resolveMessageAttachments } from "../utils/messageAttachments";

type ChatWindowProps = {
  messages: ChatMessage[];
  loading: boolean;
  approving?: boolean;
  apiOnline: boolean;
  showTimestamps: boolean;
  onSend: (message: string) => Promise<void> | void;
  onStop?: () => void;
  onEditMessage?: (index: number, newText: string) => Promise<void> | void;
  onApproveSkill?: (approved: boolean) => Promise<void> | void;
  onOpenSettings: () => void;
  onOpenUpload: () => void;
  onOpenSidebar: () => void;
};

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

const COMPOSER_MAX_PX = 160;
const SCROLL_EDGE_PX = 56;

function autosizeTextarea(el: HTMLTextAreaElement | null) {
  if (!el) return;
  el.style.height = "auto";
  el.style.height = `${Math.min(el.scrollHeight, COMPOSER_MAX_PX)}px`;
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

function LoadingBubble() {
  return (
    <div className="mb-4 flex items-start gap-3">
      <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-2xl bg-primary/15">
        <Sparkles size={14} className="text-primary" />
      </div>
      <div className="flex min-h-[44px] min-w-[56px] items-center justify-center rounded-3xl rounded-tl-sm border border-border bg-card px-5 py-3 shadow-sm">
        <LoaderCircle className="animate-spin text-primary" size={20} />
      </div>
    </div>
  );
}

function AssistantText({
  text,
  animate,
}: {
  text: string;
  animate: boolean;
}) {
  const visible = useTypewriter(text, animate);
  return (
    <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">
      {visible}
    </p>
  );
}

export function ChatWindow({
  messages,
  loading,
  approving = false,
  apiOnline,
  showTimestamps,
  onSend,
  onStop,
  onEditMessage,
  onApproveSkill,
  onOpenSettings,
  onOpenUpload,
  onOpenSidebar,
}: ChatWindowProps) {
  const { resolvedTheme, setTheme } = useTheme();
  const isDark = resolvedTheme === "dark";
  const [draft, setDraft] = useState("");
  const [historyPos, setHistoryPos] = useState<number | null>(null);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [editingText, setEditingText] = useState("");
  const [viewerAttachment, setViewerAttachment] = useState<ChatAttachment | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const stickToBottomRef = useRef(true);
  const selectingRef = useRef(false);

  const last = messages[messages.length - 1];
  const waitingApproval = Boolean(
    last && last.status === "REQUIRES_APPROVAL" && last.role !== "user",
  );
  const inputLocked = loading || approving || waitingApproval;
  const showStop = loading && !approving;

  const userHistory = useMemo(
    () => messages.filter((m) => m.role === "user").map((m) => m.message),
    [messages],
  );

  function scrollListToBottom() {
    const el = listRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }

  useEffect(() => {
    autosizeTextarea(textareaRef.current);
  }, [draft, editingText, editingIndex]);

  useEffect(() => {
    const el = listRef.current;
    if (!el) return;

    const onScroll = () => {
      stickToBottomRef.current =
        el.scrollHeight - el.scrollTop - el.clientHeight < 96;
    };
    el.addEventListener("scroll", onScroll, { passive: true });

    const inner = el.firstElementChild;
    const ro =
      inner &&
      new ResizeObserver(() => {
        if (stickToBottomRef.current) scrollListToBottom();
      });
    if (inner && ro) ro.observe(inner);

    const onMouseDown = (event: MouseEvent) => {
      if (event.button === 0) selectingRef.current = true;
    };
    const onMouseUp = () => {
      selectingRef.current = false;
    };
    const onMouseMove = (event: MouseEvent) => {
      if (!selectingRef.current || event.buttons !== 1) return;
      const rect = el.getBoundingClientRect();
      if (event.clientY > rect.bottom - SCROLL_EDGE_PX) {
        el.scrollTop += Math.min(
          36,
          event.clientY - (rect.bottom - SCROLL_EDGE_PX) + 12,
        );
      } else if (event.clientY < rect.top + SCROLL_EDGE_PX) {
        el.scrollTop -= Math.min(
          36,
          rect.top + SCROLL_EDGE_PX - event.clientY + 12,
        );
      }
    };

    el.addEventListener("mousedown", onMouseDown);
    window.addEventListener("mouseup", onMouseUp);
    window.addEventListener("mousemove", onMouseMove);

    return () => {
      el.removeEventListener("scroll", onScroll);
      el.removeEventListener("mousedown", onMouseDown);
      window.removeEventListener("mouseup", onMouseUp);
      window.removeEventListener("mousemove", onMouseMove);
      ro?.disconnect();
    };
  }, [messages.length === 0]);

  useEffect(() => {
    if (stickToBottomRef.current) scrollListToBottom();
  }, [messages, loading, approving, editingIndex]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (editingIndex !== null && onEditMessage) {
      const text = editingText.trim();
      if (!text || inputLocked) return;
      const idx = editingIndex;
      setEditingIndex(null);
      setEditingText("");
      setHistoryPos(null);
      await onEditMessage(idx, text);
      return;
    }
    const text = draft.trim();
    if (!text || inputLocked) return;
    setDraft("");
    setHistoryPos(null);
    await onSend(text);
  }

  function handleDraftKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "ArrowUp" && !e.shiftKey && editingIndex === null) {
      const ta = e.currentTarget;
      if (ta.selectionStart === 0 && ta.selectionEnd === 0 && userHistory.length > 0) {
        e.preventDefault();
        const next =
          historyPos === null
            ? userHistory.length - 1
            : Math.max(0, historyPos - 1);
        setHistoryPos(next);
        setDraft(userHistory[next] ?? "");
      }
      return;
    }
    if (e.key === "ArrowDown" && !e.shiftKey && editingIndex === null && historyPos !== null) {
      e.preventDefault();
      if (historyPos >= userHistory.length - 1) {
        setHistoryPos(null);
        setDraft("");
      } else {
        const next = historyPos + 1;
        setHistoryPos(next);
        setDraft(userHistory[next] ?? "");
      }
      return;
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSubmit(e);
    }
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
            <p
              className="truncate text-sm text-foreground"
              style={{ fontWeight: 600, lineHeight: 1.2 }}
            >
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
          <h2
            className="mb-1.5 text-center text-foreground"
            style={{ fontWeight: 600, fontSize: "1.15rem" }}
          >
            ¿En qué te puedo ayudar?
          </h2>
          <p className="mb-8 max-w-sm text-center text-sm text-muted-foreground">
            Subí actas, resoluciones o planos, y preguntá por caudales, tomas o resoluciones
            específicas.
          </p>
          <div className="grid w-full max-w-4xl grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
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
        <div ref={listRef} className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto w-full px-3 py-4 sm:px-6 sm:py-6 lg:px-10 xl:px-16">
            {messages.map((msg, index) => {
              const isUser = msg.role === "user";
              const isLast = index === messages.length - 1;
              const showCard = isPendingApproval(msg, isLast);
              const msgKey = msg.id ?? `${msg.role}-${index}-${msg.created_at ?? index}`;

              if (showCard) {
                const isDownloadApproval = msg.approval_kind === "download_remote";
                const pending = isPendingApproval(msg, isLast);
                return (
                  <div key={msgKey} className="mb-4 flex items-start gap-3">
                    <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-2xl bg-primary/15">
                      <Sparkles size={14} className="text-primary" />
                    </div>
                    <div className="max-w-[min(92%,56rem)] lg:max-w-[min(88%,72rem)] xl:max-w-[min(85%,80rem)] rounded-3xl rounded-tl-sm border border-primary/30 bg-card px-4 py-3 shadow-sm">
                      {pending && (
                        <div className="mb-2 inline-flex items-center gap-1 rounded-md bg-primary/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-primary">
                          {isDownloadApproval ? "Descarga de skill" : "Autorización de ejecución"}
                        </div>
                      )}
                      <p className="text-sm leading-relaxed text-foreground">
                        {msg.message ||
                          (isDownloadApproval
                            ? "No tengo esta habilidad instalada. ¿Querés que la busque/descargue?"
                            : `Encontré la skill '${msg.skill_name || "desconocida"}'. ¿Autorizás a ejecutarla?`)}
                      </p>
                      {!isDownloadApproval && pending && msg.skill_description && (
                        <p className="mt-2 text-xs text-muted-foreground">{msg.skill_description}</p>
                      )}
                      {pending && onApproveSkill && (
                        <div className="mt-3 flex flex-wrap gap-2">
                          <button
                            type="button"
                            disabled={approving}
                            onClick={() => void onApproveSkill(true)}
                            className="inline-flex items-center gap-1.5 rounded-xl bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground transition hover:opacity-90 disabled:opacity-40"
                          >
                            {isDownloadApproval ? (
                              <>
                                <Globe size={14} />
                                Sí, descargar
                              </>
                            ) : (
                              <>
                                <ShieldCheck size={14} />
                                Autorizar
                              </>
                            )}
                          </button>
                          <button
                            type="button"
                            disabled={approving}
                            onClick={() => void onApproveSkill(false)}
                            className="inline-flex items-center gap-1.5 rounded-xl border border-border px-3 py-1.5 text-xs font-semibold text-muted-foreground transition hover:border-destructive/40 hover:text-destructive disabled:opacity-40"
                          >
                            <X size={14} />
                            {isDownloadApproval ? "No, gracias" : "Cancelar"}
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                );
              }

              const time = showTimestamps ? formatTime(msg.created_at) : null;
              const attachments = !isUser ? resolveMessageAttachments(msg) : [];
              const displayText = !isUser ? cleanMessageText(msg.message) : msg.message;

              if (isUser) {
                const isEditing = editingIndex === index;
                return (
                  <div key={msgKey} className="group mb-4 flex justify-end">
                    <div className="relative max-w-[min(92%,56rem)] lg:max-w-[min(88%,72rem)] xl:max-w-[min(85%,80rem)]">
                      {isEditing ? (
                        <div className="rounded-3xl rounded-tr-sm border border-primary/40 bg-primary/10 px-3 py-2">
                          <textarea
                            value={editingText}
                            onChange={(e) => setEditingText(e.target.value)}
                            rows={3}
                            className="w-full resize-none bg-transparent text-sm text-foreground outline-none"
                            autoFocus
                            onKeyDown={(e) => {
                              if (e.key === "Escape") {
                                setEditingIndex(null);
                                setEditingText("");
                              }
                            }}
                          />
                          <div className="mt-2 flex justify-end gap-2">
                            <button
                              type="button"
                              className="text-xs text-muted-foreground"
                              onClick={() => {
                                setEditingIndex(null);
                                setEditingText("");
                              }}
                            >
                              Cancelar
                            </button>
                            <button
                              type="button"
                              className="rounded-lg bg-primary px-2.5 py-1 text-xs font-medium text-primary-foreground"
                              disabled={!editingText.trim() || inputLocked}
                              onClick={() => {
                                const text = editingText.trim();
                                if (!text || inputLocked) return;
                                setEditingIndex(null);
                                setEditingText("");
                                void onEditMessage?.(index, text);
                              }}
                            >
                              Reenviar
                            </button>
                          </div>
                        </div>
                      ) : (
                        <>
                          <div className="rounded-3xl rounded-tr-sm bg-primary px-4 py-3 text-primary-foreground shadow-sm">
                            <p className="whitespace-pre-wrap text-sm leading-relaxed">
                              {msg.message}
                            </p>
                          </div>
                          {onEditMessage && !inputLocked && (
                            <button
                              type="button"
                              title="Editar y reenviar"
                              onClick={() => {
                                setEditingIndex(index);
                                setEditingText(msg.message);
                              }}
                              className="absolute -left-9 top-2 flex h-7 w-7 items-center justify-center rounded-lg text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 hover:bg-muted hover:text-foreground"
                            >
                              <Pencil size={14} />
                            </button>
                          )}
                        </>
                      )}
                      {time && !isEditing && (
                        <p className="mt-1 pr-1 text-right text-[10px] text-muted-foreground">
                          {time}
                        </p>
                      )}
                    </div>
                  </div>
                );
              }

              return (
                <div key={msgKey} className="mb-4 flex items-start gap-3">
                  <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-2xl bg-primary/15">
                    <Sparkles size={14} className="text-primary" />
                  </div>
                  <div className="max-w-[min(92%,56rem)] lg:max-w-[min(88%,72rem)] xl:max-w-[min(85%,80rem)]">
                    <div className="rounded-3xl rounded-tl-sm border border-border bg-card px-4 py-3 shadow-sm">
                      {msg.from_cache && (
                        <div className="mb-2 inline-flex items-center gap-1 rounded-md bg-primary/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-primary">
                          Caché semántico
                        </div>
                      )}
                      <AssistantText text={displayText} animate={Boolean(msg.animate)} />
                      {attachments.map((attachment) => (
                        <AttachmentCard
                          key={attachment.file_id}
                          attachment={attachment}
                          onOpen={setViewerAttachment}
                        />
                      ))}
                    </div>
                    {time && (
                      <p className="mt-1 pl-1 text-[10px] text-muted-foreground">{time}</p>
                    )}
                  </div>
                </div>
              );
            })}

            {loading && !approving && <LoadingBubble />}
            {approving && (
              <div className="mb-4 flex items-start gap-3">
                <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-2xl bg-primary/15">
                  <Sparkles size={14} className="text-primary" />
                </div>
                <div className="flex min-h-[44px] items-center gap-2 rounded-3xl rounded-tl-sm border border-border bg-card px-4 py-3 text-sm text-muted-foreground shadow-sm">
                  <LoaderCircle className="animate-spin" size={16} />
                  Gemini audita la skill…
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        </div>
      )}

      <form
        onSubmit={handleSubmit}
        className="shrink-0 px-3 pt-2 pb-[max(1rem,env(safe-area-inset-bottom))] sm:px-6 lg:px-10 xl:px-16 sm:pb-4"
      >
        {waitingApproval && (
          <p className="mx-auto mb-2 max-w-6xl px-1 text-xs text-muted-foreground">
            Autorizá o cancelá la skill pendiente para continuar el chat.
          </p>
        )}
        <div className="mx-auto flex w-full items-end gap-1.5 rounded-3xl border border-border bg-card px-2.5 py-2 shadow-sm transition-all duration-200 focus-within:border-primary/40 focus-within:shadow-md sm:gap-2 sm:px-3 sm:py-2.5">
          <button
            type="button"
            onClick={onOpenUpload}
            title="Indexar documentos"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-muted-foreground transition-all hover:bg-primary/10 hover:text-primary sm:h-8 sm:w-8"
          >
            <Paperclip size={17} />
          </button>

          <textarea
            ref={textareaRef}
            value={editingIndex !== null ? editingText : draft}
            onChange={(e) =>
              editingIndex !== null
                ? setEditingText(e.target.value)
                : setDraft(e.target.value)
            }
            rows={1}
            placeholder={
              waitingApproval
                ? "Pendiente de autorización…"
                : editingIndex !== null
                  ? "Editá tu mensaje y reenviá…"
                  : "Escribí tu consulta técnica…"
            }
            disabled={inputLocked && editingIndex === null}
            className="max-h-40 min-h-9 flex-1 resize-none overflow-y-auto bg-transparent py-1 text-sm text-foreground outline-none placeholder:text-muted-foreground/60 disabled:opacity-50 sm:min-h-8"
            style={{ lineHeight: "1.5", height: "36px" }}
            onKeyDown={handleDraftKeyDown}
            onInput={(e) => autosizeTextarea(e.currentTarget)}
          />

          {showStop ? (
            <button
              type="button"
              title="Detener"
              onClick={() => onStop?.()}
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-destructive text-destructive-foreground shadow-sm transition hover:opacity-90 sm:h-8 sm:w-8"
            >
              <Square size={14} fill="currentColor" />
            </button>
          ) : (
            <button
              type="submit"
              disabled={
                inputLocked ||
                (editingIndex !== null ? !editingText.trim() : !draft.trim())
              }
              className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl transition-all duration-200 sm:h-8 sm:w-8 ${
                !inputLocked &&
                (editingIndex !== null ? editingText.trim() : draft.trim())
                  ? "bg-primary text-primary-foreground shadow-sm hover:opacity-90"
                  : "cursor-not-allowed bg-muted text-muted-foreground"
              }`}
            >
              <Send size={15} />
            </button>
          )}
        </div>

        <p className="mx-auto mt-2 max-w-6xl text-center text-[10px] text-muted-foreground/50">
          El asistente puede cometer errores. Verificá la información crítica.
        </p>
      </form>

      {viewerAttachment && (
        <FileViewerModal
          attachment={viewerAttachment}
          open={Boolean(viewerAttachment)}
          onClose={() => setViewerAttachment(null)}
        />
      )}
    </main>
  );
}
