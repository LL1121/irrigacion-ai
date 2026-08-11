import { useEffect, useRef, useState, type FormEvent } from "react";
import { LoaderCircle, SendHorizontal, Sparkles } from "lucide-react";
import type { ChatMessage } from "../services/api";

type ChatWindowProps = {
  messages: ChatMessage[];
  loading: boolean;
  onSend: (message: string) => Promise<void> | void;
};

export function ChatWindow({ messages, loading, onSend }: ChatWindowProps) {
  const [draft, setDraft] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || loading) return;
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
          return (
            <div
              key={`${msg.role}-${index}-${msg.created_at ?? index}`}
              className={`flex ${isUser ? "justify-end" : "justify-start"}`}
            >
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
            </div>
          );
        })}

        {loading && (
          <div className="flex justify-start">
            <div className="inline-flex items-center gap-2 rounded-2xl rounded-bl-md border border-border bg-panel-2 px-4 py-3 text-sm text-muted">
              <LoaderCircle className="animate-spin" size={16} />
              Analizando contexto…
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <form
        onSubmit={handleSubmit}
        className="border-t border-border bg-panel/60 px-6 py-4 backdrop-blur"
      >
        <div className="flex items-end gap-3 rounded-xl border border-border bg-panel-2 p-2 focus-within:border-accent/40">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={2}
            placeholder="Escribí tu consulta técnica…"
            className="max-h-40 min-h-[52px] flex-1 resize-none bg-transparent px-2 py-2 text-sm text-text outline-none placeholder:text-muted"
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void handleSubmit(e);
              }
            }}
          />
          <button
            type="submit"
            disabled={loading || !draft.trim()}
            className="mb-1 inline-flex h-10 w-10 items-center justify-center rounded-lg bg-accent text-ink transition hover:bg-accent-dim disabled:cursor-not-allowed disabled:opacity-40"
          >
            <SendHorizontal size={16} />
          </button>
        </div>
      </form>
    </section>
  );
}
