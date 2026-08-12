import { useState } from "react";
import { Plus, MessageSquare, Trash2, Search, X } from "lucide-react";
import { Button } from "./ui/button";
import { ScrollArea } from "./ui/scroll-area";
import { Separator } from "./ui/separator";

export interface Conversation {
  id: string;
  title: string;
  preview: string;
  timestamp: Date;
  messages: ChatMessage[];
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  attachments?: FileAttachment[];
}

export interface FileAttachment {
  id: string;
  name: string;
  type: "image" | "pdf" | "document" | "code" | "other";
  size: string;
  dataUrl?: string;
}

interface ChatSidebarProps {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  open: boolean;
  onClose: () => void;
}

function groupByDate(conversations: Conversation[]) {
  const now = new Date();
  const today: Conversation[] = [];
  const yesterday: Conversation[] = [];
  const week: Conversation[] = [];
  const older: Conversation[] = [];

  conversations.forEach((c) => {
    const diff = (now.getTime() - c.timestamp.getTime()) / (1000 * 60 * 60 * 24);
    if (diff < 1) today.push(c);
    else if (diff < 2) yesterday.push(c);
    else if (diff < 7) week.push(c);
    else older.push(c);
  });

  return { today, yesterday, week, older };
}

export function ChatSidebar({
  conversations,
  activeId,
  onSelect,
  onNew,
  onDelete,
  open,
  onClose,
}: ChatSidebarProps) {
  const [search, setSearch] = useState("");
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  const filtered = conversations.filter(
    (c) =>
      c.title.toLowerCase().includes(search.toLowerCase()) ||
      c.preview.toLowerCase().includes(search.toLowerCase())
  );

  const { today, yesterday, week, older } = groupByDate(filtered);

  const ConvItem = ({ conv }: { conv: Conversation }) => {
    const isActive = activeId === conv.id;
    const isHovered = hoveredId === conv.id;

    return (
      <div
        className={`group relative flex items-start gap-3 px-3 py-2.5 rounded-xl cursor-pointer transition-all duration-150 ${
          isActive
            ? "bg-primary/10 border border-primary/20"
            : "hover:bg-muted/60"
        }`}
        onClick={() => onSelect(conv.id)}
        onMouseEnter={() => setHoveredId(conv.id)}
        onMouseLeave={() => setHoveredId(null)}
      >
        <div
          className={`mt-0.5 shrink-0 w-7 h-7 rounded-lg flex items-center justify-center transition-colors ${
            isActive ? "bg-primary/20" : "bg-muted"
          }`}
        >
          <MessageSquare
            size={13}
            className={isActive ? "text-primary" : "text-muted-foreground"}
          />
        </div>

        <div className="flex-1 min-w-0 pr-6">
          <p
            className={`text-sm truncate leading-snug ${
              isActive ? "text-primary font-medium" : "text-foreground"
            }`}
            style={{ fontWeight: isActive ? 500 : 400 }}
          >
            {conv.title}
          </p>
          <p className="text-xs text-muted-foreground truncate mt-0.5">
            {conv.preview}
          </p>
        </div>

        {(isHovered || isActive) && (
          <button
            className="absolute right-2 top-2.5 w-6 h-6 flex items-center justify-center rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-all"
            onClick={(e) => {
              e.stopPropagation();
              onDelete(conv.id);
            }}
          >
            <Trash2 size={12} />
          </button>
        )}
      </div>
    );
  };

  const Section = ({
    label,
    items,
  }: {
    label: string;
    items: Conversation[];
  }) => {
    if (items.length === 0) return null;
    return (
      <div className="mb-3">
        <p className="px-3 mb-1.5 text-[11px] uppercase tracking-wider text-muted-foreground/70 font-medium">
          {label}
        </p>
        <div className="flex flex-col gap-0.5">
          {items.map((c) => (
            <ConvItem key={c.id} conv={c} />
          ))}
        </div>
      </div>
    );
  };

  return (
    <>
      {/* Mobile overlay */}
      {open && (
        <div
          className="fixed inset-0 bg-black/20 z-30 lg:hidden"
          onClick={onClose}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`
          fixed lg:relative top-0 left-0 h-full z-40 lg:z-auto
          w-72 flex flex-col bg-sidebar border-r border-sidebar-border
          transition-transform duration-300 ease-in-out
          ${open ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}
        `}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 pt-5 pb-3">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-primary flex items-center justify-center shadow-sm">
              <span className="text-primary-foreground text-sm font-semibold">A</span>
            </div>
            <div>
              <p className="text-sm text-foreground" style={{ fontWeight: 600, lineHeight: 1.2 }}>
                Asistente IA
              </p>
              <p className="text-[10px] text-muted-foreground">Siempre disponible</p>
            </div>
          </div>
          <button
            className="lg:hidden w-7 h-7 flex items-center justify-center rounded-lg hover:bg-muted transition-colors"
            onClick={onClose}
          >
            <X size={15} className="text-muted-foreground" />
          </button>
        </div>

        {/* New chat button */}
        <div className="px-3 mb-3">
          <Button
            onClick={onNew}
            className="w-full justify-start gap-2.5 rounded-xl shadow-none border border-primary/20 bg-primary/8 hover:bg-primary/15 text-primary h-9"
            variant="ghost"
          >
            <Plus size={15} />
            <span className="text-sm">Nueva conversación</span>
          </Button>
        </div>

        {/* Search */}
        <div className="px-3 mb-3">
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
              className="w-full pl-8 pr-3 py-2 text-sm rounded-xl bg-muted/60 border border-border placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-ring transition-all"
            />
            {search && (
              <button
                onClick={() => setSearch("")}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                <X size={12} />
              </button>
            )}
          </div>
        </div>

        <Separator className="mb-3 opacity-50" />

        {/* History */}
        <ScrollArea className="flex-1 px-2">
          {filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center px-4">
              <MessageSquare size={28} className="text-muted-foreground/40 mb-3" />
              <p className="text-sm text-muted-foreground">
                {search ? "Sin resultados" : "No hay conversaciones aún"}
              </p>
            </div>
          ) : (
            <div className="pb-4">
              <Section label="Hoy" items={today} />
              <Section label="Ayer" items={yesterday} />
              <Section label="Esta semana" items={week} />
              <Section label="Anteriores" items={older} />
            </div>
          )}
        </ScrollArea>
      </aside>
    </>
  );
}
