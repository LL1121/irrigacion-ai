import { useEffect, useRef, useState, type FormEvent } from "react";
import { LoaderCircle, SendHorizontal, ShieldCheck, Sparkles, X } from "lucide-react";
import type { ChatMessage } from "../services/api";

type ChatWindowProps = {
  messages: ChatMessage[];
  loading: boolean;
  approving?: boolean;
  onSend: (message: string) => Promise<void> | void;
  onApproveSkill?: (approved: boolean) => Promise<void> | void;
};

function isPendingApproval(msg: ChatMessage, isLast: boolean): boolean {
  return isLast && msg.status === "REQUIRES_APPROVAL" && msg.role !== "user";
}

export function ChatWindow({
  messages,
  loading,
  approving = false,
  onSend,
  onApproveSkill,
}: ChatWindowProps) {
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
    <section className="flex h-full min-w-0 flex-1 flex-col">
      <header className="flex items-center justify-between border-b border-border px-6 py-4">
        <div>
          <h2 className="text-base font-semibold text-text">Consulta técnica</h2>
          <p className="text-xs text-muted">
            Respuestas basadas en documentos indexados y memoria de sesión
          </p>
        </div>
      </header>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-6 py-5">
        {messages.length === 0 && !loading && (
          <div className="mx-auto mt-16 max-w-md text-center">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-accent/10 text-accent">
              <Sparkles size={20} />
            </div>
            <p className="text-sm text-muted">
              Subí actas, resoluciones o planos, y preguntá por caudales,
              tomas o resoluciones específicas.
            </p>
          </div>
        )}

        {messages.map((msg, index) => {
          const isUser = msg.role === "user";
          const isLast = index === messages.length - 1;
          const showCard = msg.status === "REQUIRES_APPROVAL" && !isUser;
          return (
            <div
              key={`${msg.role}-${index}-${msg.created_at ?? index}`}
              className={`flex ${isUser ? "justify-end" : "justify-start"}`}
            >
              {showCard ? (
                <div className="max-w-[78%] rounded-2xl rounded-bl-md border border-accent/40 bg-panel-2 px-4 py-3 text-sm leading-relaxed shadow-sm">
                  <div className="mb-2 inline-flex items-center gap-1 rounded-md bg-accent/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-accent">
                    Autorización de skill
                  </div>
                  <p className="text-text">
                    No tengo esta habilidad. Se encontró la skill{" "}
                    <span className="font-semibold text-accent">
                      '{msg.skill_name || "desconocida"}'
                    </span>
                    . ¿Autorizas a Gemini a auditarla y ejecutarla en el Sandbox?
                  </p>
                  {msg.skill_description && (
                    <p className="mt-2 text-xs text-muted">{msg.skill_description}</p>
                  )}
                  {isPendingApproval(msg, isLast) && onApproveSkill && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      <button
                        type="button"
                        disabled={approving}
                        onClick={() => void onApproveSkill(true)}
                        className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-ink transition hover:bg-accent-dim disabled:opacity-40"
                      >
                        <ShieldCheck size={14} />
                        Autorizar
                      </button>
                      <button
                        type="button"
                        disabled={approving}
                        onClick={() => void onApproveSkill(false)}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-semibold text-muted transition hover:border-danger hover:text-danger disabled:opacity-40"
                      >
                        <X size={14} />
                        Cancelar
                      </button>
                    </div>
                  )}
                </div>
              ) : (
                <div
                  className={`max-w-[78%] rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm ${
                    isUser
                      ? "rounded-br-md bg-user text-text"
                      : "rounded-bl-md border border-border bg-panel-2 text-text"
                  }`}
                >
                  {!isUser && msg.from_cache && (
                    <div className="mb-2 inline-flex items-center gap-1 rounded-md bg-accent/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-accent">
                      Caché semántico
                    </div>
                  )}
                  <div className="whitespace-pre-wrap">{msg.message}</div>
                </div>
              )}
            </div>
          );
        })}

        {(loading || approving) && (
          <div className="flex justify-start">
            <div className="inline-flex items-center gap-2 rounded-2xl rounded-bl-md border border-border bg-panel-2 px-4 py-3 text-sm text-muted">
              <LoaderCircle className="animate-spin" size={16} />
              {approving
                ? "Gemini audita y el sandbox ejecuta la skill…"
                : "Analizando contexto…"}
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <form
        onSubmit={handleSubmit}
        className="border-t border-border bg-panel/60 px-6 py-4 backdrop-blur"
      >
        {waitingApproval && (
          <p className="mb-2 text-xs text-muted">
            Autorizá o cancelá la skill pendiente para continuar el chat.
          </p>
        )}
        <div className="flex items-end gap-3 rounded-xl border border-border bg-panel-2 p-2 focus-within:border-accent/40">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={2}
            placeholder={
              waitingApproval
                ? "Pendiente de autorización…"
                : "Escribí tu consulta técnica…"
            }
            disabled={inputLocked}
            className="max-h-40 min-h-[52px] flex-1 resize-none bg-transparent px-2 py-2 text-sm text-text outline-none placeholder:text-muted disabled:opacity-50"
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
            className="mb-1 inline-flex h-10 w-10 items-center justify-center rounded-lg bg-accent text-ink transition hover:bg-accent-dim disabled:cursor-not-allowed disabled:opacity-40"
          >
            <SendHorizontal size={16} />
          </button>
        </div>
      </form>
    </section>
  );
}
