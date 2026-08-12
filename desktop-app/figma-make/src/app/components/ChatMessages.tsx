import { useEffect, useRef } from "react";
import {
  FileText,
  Image as ImageIcon,
  Code2,
  File,
  Sparkles,
  Lightbulb,
  PenLine,
  Globe,
  BookOpen,
  Calculator,
} from "lucide-react";
import { ScrollArea } from "./ui/scroll-area";
import type { ChatMessage, FileAttachment } from "./ChatSidebar";

interface ChatMessagesProps {
  messages: ChatMessage[];
  isTyping: boolean;
  onSuggestedPrompt: (prompt: string) => void;
}

const SUGGESTED_PROMPTS = [
  {
    icon: PenLine,
    label: "Redactar un correo",
    prompt: "Ayúdame a redactar un correo profesional para presentar mi servicio a un cliente potencial.",
  },
  {
    icon: Lightbulb,
    label: "Ideas de negocio",
    prompt: "Dame 5 ideas innovadoras para un negocio pequeño que pueda comenzar con poco capital.",
  },
  {
    icon: Globe,
    label: "Traducir texto",
    prompt: "Necesito traducir un texto del español al inglés de forma clara y profesional.",
  },
  {
    icon: BookOpen,
    label: "Explicar un tema",
    prompt: "Explícame de forma sencilla cómo funciona la inteligencia artificial y para qué sirve.",
  },
  {
    icon: Calculator,
    label: "Resolver un problema",
    prompt: "Ayúdame a resolver un problema matemático paso a paso.",
  },
  {
    icon: Code2,
    label: "Analizar un archivo",
    prompt: "Puedo adjuntar un archivo y necesito que me ayudes a analizarlo.",
  },
];

function FileCard({ attachment }: { attachment: FileAttachment }) {
  const icons = {
    image: ImageIcon,
    pdf: FileText,
    document: FileText,
    code: Code2,
    other: File,
  };

  const colors = {
    image: "text-blue-500 bg-blue-50 dark:bg-blue-950/30",
    pdf: "text-red-500 bg-red-50 dark:bg-red-950/30",
    document: "text-amber-600 bg-amber-50 dark:bg-amber-950/30",
    code: "text-emerald-600 bg-emerald-50 dark:bg-emerald-950/30",
    other: "text-muted-foreground bg-muted",
  };

  const Icon = icons[attachment.type];
  const colorClass = colors[attachment.type];

  if (attachment.type === "image" && attachment.dataUrl) {
    return (
      <div className="rounded-xl overflow-hidden border border-border max-w-48">
        <img
          src={attachment.dataUrl}
          alt={attachment.name}
          className="w-full h-32 object-cover"
        />
        <div className="px-2.5 py-1.5 bg-card/80">
          <p className="text-xs text-muted-foreground truncate">{attachment.name}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2.5 rounded-xl border border-border bg-card/60 px-3 py-2 max-w-52">
      <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${colorClass}`}>
        <Icon size={15} />
      </div>
      <div className="min-w-0">
        <p className="text-xs truncate text-foreground" style={{ fontWeight: 500 }}>
          {attachment.name}
        </p>
        <p className="text-[10px] text-muted-foreground">{attachment.size}</p>
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex items-start gap-3 mb-4">
      <div className="w-8 h-8 rounded-2xl bg-primary/15 flex items-center justify-center shrink-0 mt-0.5">
        <Sparkles size={14} className="text-primary" />
      </div>
      <div className="bg-card border border-border rounded-3xl rounded-tl-sm px-4 py-3 shadow-sm">
        <div className="flex items-center gap-1.5">
          <span
            className="w-2 h-2 rounded-full bg-primary/50 animate-bounce"
            style={{ animationDelay: "0ms" }}
          />
          <span
            className="w-2 h-2 rounded-full bg-primary/50 animate-bounce"
            style={{ animationDelay: "160ms" }}
          />
          <span
            className="w-2 h-2 rounded-full bg-primary/50 animate-bounce"
            style={{ animationDelay: "320ms" }}
          />
        </div>
      </div>
    </div>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  const formatTime = (date: Date) =>
    date.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });

  if (isUser) {
    return (
      <div className="flex justify-end mb-4">
        <div className="max-w-[75%]">
          {message.attachments && message.attachments.length > 0 && (
            <div className="flex flex-wrap gap-2 justify-end mb-2">
              {message.attachments.map((a) => (
                <FileCard key={a.id} attachment={a} />
              ))}
            </div>
          )}
          {message.content && (
            <div className="bg-primary text-primary-foreground rounded-3xl rounded-tr-sm px-4 py-3 shadow-sm">
              <p className="text-sm leading-relaxed whitespace-pre-wrap">{message.content}</p>
            </div>
          )}
          <p className="text-[10px] text-muted-foreground text-right mt-1 pr-1">
            {formatTime(message.timestamp)}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-start gap-3 mb-4">
      <div className="w-8 h-8 rounded-2xl bg-primary/15 flex items-center justify-center shrink-0 mt-0.5">
        <Sparkles size={14} className="text-primary" />
      </div>
      <div className="max-w-[78%]">
        {message.attachments && message.attachments.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-2">
            {message.attachments.map((a) => (
              <FileCard key={a.id} attachment={a} />
            ))}
          </div>
        )}
        <div className="bg-card border border-border rounded-3xl rounded-tl-sm px-4 py-3 shadow-sm">
          <p className="text-sm leading-relaxed text-foreground whitespace-pre-wrap">
            {message.content}
          </p>
        </div>
        <p className="text-[10px] text-muted-foreground mt-1 pl-1">
          {formatTime(message.timestamp)}
        </p>
      </div>
    </div>
  );
}

export function ChatMessages({
  messages,
  isTyping,
  onSuggestedPrompt,
}: ChatMessagesProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isTyping]);

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center px-6 py-8 overflow-y-auto">
        <div className="w-16 h-16 rounded-3xl bg-primary/15 flex items-center justify-center mb-5 shadow-sm">
          <Sparkles size={28} className="text-primary" />
        </div>
        <h2 className="text-foreground mb-1.5" style={{ fontWeight: 600, fontSize: "1.25rem" }}>
          ¿En qué te puedo ayudar?
        </h2>
        <p className="text-muted-foreground text-sm text-center mb-8 max-w-sm">
          Puedo ayudarte a redactar, explicar, traducir, analizar archivos y mucho más.
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 w-full max-w-2xl">
          {SUGGESTED_PROMPTS.map(({ icon: Icon, label, prompt }) => (
            <button
              key={label}
              onClick={() => onSuggestedPrompt(prompt)}
              className="flex items-start gap-3 p-4 rounded-2xl border border-border bg-card hover:bg-accent hover:border-primary/25 text-left transition-all duration-150 group shadow-sm"
            >
              <div className="w-8 h-8 rounded-xl bg-primary/10 flex items-center justify-center shrink-0 group-hover:bg-primary/20 transition-colors">
                <Icon size={15} className="text-primary" />
              </div>
              <div>
                <p className="text-sm text-foreground leading-snug" style={{ fontWeight: 500 }}>
                  {label}
                </p>
                <p className="text-xs text-muted-foreground mt-0.5 leading-snug line-clamp-2">
                  {prompt.slice(0, 60)}...
                </p>
              </div>
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <ScrollArea className="flex-1">
      <div className="px-4 py-6 max-w-3xl mx-auto">
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        {isTyping && <TypingIndicator />}
        <div ref={bottomRef} />
      </div>
    </ScrollArea>
  );
}
