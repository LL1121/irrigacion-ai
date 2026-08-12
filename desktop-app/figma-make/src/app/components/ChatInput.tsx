import { useRef, useState, useCallback, KeyboardEvent } from "react";
import {
  Paperclip,
  Send,
  X,
  Image as ImageIcon,
  FileText,
  Code2,
  File,
  Mic,
  StopCircle,
} from "lucide-react";
import { Button } from "./ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "./ui/tooltip";
import type { FileAttachment } from "./ChatSidebar";

interface ChatInputProps {
  onSend: (content: string, attachments: FileAttachment[]) => void;
  disabled?: boolean;
}

const ACCEPT_TYPES =
  "image/*,.pdf,.doc,.docx,.txt,.md,.js,.ts,.tsx,.jsx,.py,.json,.csv,.xlsx";

function getFileType(file: File): FileAttachment["type"] {
  if (file.type.startsWith("image/")) return "image";
  if (file.type === "application/pdf") return "pdf";
  if (
    file.type.includes("word") ||
    file.type.includes("text/plain") ||
    file.name.endsWith(".md") ||
    file.name.endsWith(".txt") ||
    file.name.endsWith(".csv")
  )
    return "document";
  if (
    file.name.endsWith(".js") ||
    file.name.endsWith(".ts") ||
    file.name.endsWith(".tsx") ||
    file.name.endsWith(".jsx") ||
    file.name.endsWith(".py") ||
    file.name.endsWith(".json")
  )
    return "code";
  return "other";
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const fileIconMap = {
  image: ImageIcon,
  pdf: FileText,
  document: FileText,
  code: Code2,
  other: File,
};

const fileColorMap = {
  image: "text-blue-500 bg-blue-50 dark:bg-blue-950/30",
  pdf: "text-red-500 bg-red-50 dark:bg-red-950/30",
  document: "text-amber-600 bg-amber-50 dark:bg-amber-950/30",
  code: "text-emerald-600 bg-emerald-50 dark:bg-emerald-950/30",
  other: "text-muted-foreground bg-muted",
};

export function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [text, setText] = useState("");
  const [attachments, setAttachments] = useState<FileAttachment[]>([]);
  const [isRecording, setIsRecording] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const canSend = (text.trim().length > 0 || attachments.length > 0) && !disabled;

  const handleFiles = useCallback((files: FileList) => {
    Array.from(files).forEach((file) => {
      const type = getFileType(file);
      const id = `${Date.now()}-${Math.random()}`;

      if (type === "image") {
        const reader = new FileReader();
        reader.onload = (e) => {
          setAttachments((prev) => [
            ...prev,
            {
              id,
              name: file.name,
              type,
              size: formatSize(file.size),
              dataUrl: e.target?.result as string,
            },
          ]);
        };
        reader.readAsDataURL(file);
      } else {
        setAttachments((prev) => [
          ...prev,
          { id, name: file.name, type, size: formatSize(file.size) },
        ]);
      }
    });
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      if (e.dataTransfer.files.length > 0) handleFiles(e.dataTransfer.files);
    },
    [handleFiles]
  );

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleSend = () => {
    if (!canSend) return;
    onSend(text.trim(), attachments);
    setText("");
    setAttachments([]);
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleTextChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setText(e.target.value);
    const ta = e.target;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 160)}px`;
  };

  const removeAttachment = (id: string) => {
    setAttachments((prev) => prev.filter((a) => a.id !== id));
  };

  const toggleRecording = () => {
    setIsRecording((v) => !v);
    if (isRecording) {
      setIsRecording(false);
    }
  };

  return (
    <TooltipProvider delayDuration={400}>
      <div
        className="px-4 pb-4 pt-2"
        onDrop={handleDrop}
        onDragOver={(e) => e.preventDefault()}
      >
        {/* Attached files preview */}
        {attachments.length > 0 && (
          <div className="flex gap-2 flex-wrap mb-2 px-1">
            {attachments.map((att) => {
              const Icon = fileIconMap[att.type];
              const colorClass = fileColorMap[att.type];

              return (
                <div
                  key={att.id}
                  className="relative group flex items-center gap-2 bg-card border border-border rounded-xl px-3 py-2 shadow-sm max-w-44"
                >
                  {att.type === "image" && att.dataUrl ? (
                    <img
                      src={att.dataUrl}
                      alt={att.name}
                      className="w-8 h-8 rounded-lg object-cover shrink-0"
                    />
                  ) : (
                    <div
                      className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${colorClass}`}
                    >
                      <Icon size={13} />
                    </div>
                  )}
                  <div className="min-w-0">
                    <p className="text-xs truncate text-foreground" style={{ fontWeight: 500 }}>
                      {att.name}
                    </p>
                    <p className="text-[10px] text-muted-foreground">{att.size}</p>
                  </div>
                  <button
                    onClick={() => removeAttachment(att.id)}
                    className="absolute -top-1.5 -right-1.5 w-4.5 h-4.5 bg-muted-foreground/80 hover:bg-destructive text-white rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                    style={{ width: 18, height: 18 }}
                  >
                    <X size={9} />
                  </button>
                </div>
              );
            })}
          </div>
        )}

        {/* Input box */}
        <div className="flex items-end gap-2 bg-card border border-border rounded-3xl px-3 py-2.5 shadow-sm focus-within:border-primary/40 focus-within:shadow-md transition-all duration-200">
          {/* Attach button */}
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={disabled}
                className="shrink-0 w-8 h-8 rounded-xl flex items-center justify-center text-muted-foreground hover:text-primary hover:bg-primary/10 transition-all disabled:opacity-40"
              >
                <Paperclip size={17} />
              </button>
            </TooltipTrigger>
            <TooltipContent side="top">
              <p className="text-xs">Adjuntar archivo</p>
            </TooltipContent>
          </Tooltip>

          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={ACCEPT_TYPES}
            className="hidden"
            onChange={(e) => e.target.files && handleFiles(e.target.files)}
          />

          {/* Textarea */}
          <textarea
            ref={textareaRef}
            value={text}
            onChange={handleTextChange}
            onKeyDown={handleKeyDown}
            placeholder="Escribe tu mensaje... (Enter para enviar)"
            disabled={disabled}
            rows={1}
            className="flex-1 resize-none bg-transparent text-sm text-foreground placeholder:text-muted-foreground/60 focus:outline-none min-h-[32px] max-h-40 py-1 disabled:opacity-50"
            style={{ lineHeight: "1.5" }}
          />

          {/* Mic button */}
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={toggleRecording}
                disabled={disabled}
                className={`shrink-0 w-8 h-8 rounded-xl flex items-center justify-center transition-all disabled:opacity-40 ${
                  isRecording
                    ? "text-red-500 bg-red-50 dark:bg-red-950/30 animate-pulse"
                    : "text-muted-foreground hover:text-primary hover:bg-primary/10"
                }`}
              >
                {isRecording ? <StopCircle size={17} /> : <Mic size={17} />}
              </button>
            </TooltipTrigger>
            <TooltipContent side="top">
              <p className="text-xs">{isRecording ? "Detener grabación" : "Grabar mensaje de voz"}</p>
            </TooltipContent>
          </Tooltip>

          {/* Send button */}
          <button
            onClick={handleSend}
            disabled={!canSend}
            className={`shrink-0 w-8 h-8 rounded-xl flex items-center justify-center transition-all duration-200 ${
              canSend
                ? "bg-primary text-primary-foreground hover:opacity-90 shadow-sm"
                : "bg-muted text-muted-foreground cursor-not-allowed"
            }`}
          >
            <Send size={15} />
          </button>
        </div>

        <p className="text-center text-[10px] text-muted-foreground/50 mt-2">
          El asistente puede cometer errores. Verifica la información importante.
        </p>
      </div>
    </TooltipProvider>
  );
}
