import { X, Moon, Sun, Monitor, Volume2, VolumeX, Globe, Cpu, ChevronRight, Info, MessageSquare, Bell, Shield } from "lucide-react";
import { Switch } from "./ui/switch";
import { Separator } from "./ui/separator";
import { ScrollArea } from "./ui/scroll-area";

interface SettingsPanelProps {
  open: boolean;
  onClose: () => void;
  theme: "light" | "dark" | "system";
  onThemeChange: (t: "light" | "dark" | "system") => void;
  model: string;
  onModelChange: (m: string) => void;
  sound: boolean;
  onSoundChange: (v: boolean) => void;
  notifications: boolean;
  onNotificationsChange: (v: boolean) => void;
  language: string;
  onLanguageChange: (l: string) => void;
}

const THEMES = [
  { id: "light" as const, icon: Sun, label: "Día" },
  { id: "dark" as const, icon: Moon, label: "Noche" },
  { id: "system" as const, icon: Monitor, label: "Sistema" },
];

const MODELS = [
  { id: "gpt-4o", name: "GPT-4o", desc: "Más capaz, más lento" },
  { id: "gpt-4o-mini", name: "GPT-4o Mini", desc: "Rápido y eficiente" },
  { id: "claude-3-5-sonnet", name: "Claude 3.5 Sonnet", desc: "Excelente en análisis" },
  { id: "gemini-1-5-pro", name: "Gemini 1.5 Pro", desc: "Contexto muy largo" },
];

const LANGUAGES = [
  { id: "es", label: "Español" },
  { id: "en", label: "English" },
  { id: "pt", label: "Português" },
  { id: "fr", label: "Français" },
];

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-6">
      <p className="text-[11px] uppercase tracking-wider text-muted-foreground/70 font-medium mb-3 px-1">
        {title}
      </p>
      <div className="flex flex-col gap-2">{children}</div>
    </div>
  );
}

function SettingRow({
  icon: Icon,
  label,
  desc,
  children,
}: {
  icon: React.ElementType;
  label: string;
  desc?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-3 py-2.5 px-3 rounded-xl bg-card border border-border/60">
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded-xl bg-muted flex items-center justify-center shrink-0">
          <Icon size={15} className="text-muted-foreground" />
        </div>
        <div>
          <p className="text-sm text-foreground" style={{ fontWeight: 500 }}>
            {label}
          </p>
          {desc && <p className="text-xs text-muted-foreground">{desc}</p>}
        </div>
      </div>
      {children}
    </div>
  );
}

export function SettingsPanel({
  open,
  onClose,
  theme,
  onThemeChange,
  model,
  onModelChange,
  sound,
  onSoundChange,
  notifications,
  onNotificationsChange,
  language,
  onLanguageChange,
}: SettingsPanelProps) {
  return (
    <>
      {/* Backdrop */}
      {open && (
        <div
          className="fixed inset-0 bg-black/20 z-40 backdrop-blur-sm"
          onClick={onClose}
        />
      )}

      {/* Panel */}
      <aside
        className={`
          fixed top-0 right-0 h-full z-50 w-full max-w-sm bg-background border-l border-border shadow-2xl
          transition-transform duration-300 ease-in-out flex flex-col
          ${open ? "translate-x-0" : "translate-x-full"}
        `}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 pt-5 pb-4 border-b border-border">
          <div>
            <h2 className="text-foreground" style={{ fontWeight: 600, fontSize: "1rem" }}>
              Configuración
            </h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Personaliza tu experiencia
            </p>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-xl flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-all"
          >
            <X size={16} />
          </button>
        </div>

        <ScrollArea className="flex-1">
          <div className="px-4 py-5">

            {/* Theme */}
            <Section title="Apariencia">
              <div className="flex gap-2 p-1 bg-muted rounded-2xl">
                {THEMES.map(({ id, icon: Icon, label }) => (
                  <button
                    key={id}
                    onClick={() => onThemeChange(id)}
                    className={`flex-1 flex flex-col items-center gap-1.5 py-3 rounded-xl text-xs transition-all duration-200 ${
                      theme === id
                        ? "bg-card text-primary shadow-sm border border-border"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                    style={{ fontWeight: theme === id ? 500 : 400 }}
                  >
                    <Icon size={16} />
                    {label}
                  </button>
                ))}
              </div>
            </Section>

            {/* Model */}
            <Section title="Modelo de IA">
              <div className="flex flex-col gap-1.5">
                {MODELS.map((m) => (
                  <button
                    key={m.id}
                    onClick={() => onModelChange(m.id)}
                    className={`flex items-center justify-between px-3 py-2.5 rounded-xl border text-left transition-all duration-150 ${
                      model === m.id
                        ? "border-primary/40 bg-primary/8"
                        : "border-border bg-card hover:bg-muted/50"
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <div
                        className={`w-8 h-8 rounded-xl flex items-center justify-center ${
                          model === m.id ? "bg-primary/20" : "bg-muted"
                        }`}
                      >
                        <Cpu size={14} className={model === m.id ? "text-primary" : "text-muted-foreground"} />
                      </div>
                      <div>
                        <p
                          className={`text-sm ${model === m.id ? "text-primary" : "text-foreground"}`}
                          style={{ fontWeight: model === m.id ? 500 : 400 }}
                        >
                          {m.name}
                        </p>
                        <p className="text-xs text-muted-foreground">{m.desc}</p>
                      </div>
                    </div>
                    {model === m.id && (
                      <div className="w-2 h-2 rounded-full bg-primary" />
                    )}
                  </button>
                ))}
              </div>
            </Section>

            {/* Language */}
            <Section title="Idioma">
              <div className="grid grid-cols-2 gap-1.5">
                {LANGUAGES.map((l) => (
                  <button
                    key={l.id}
                    onClick={() => onLanguageChange(l.id)}
                    className={`flex items-center gap-2 px-3 py-2 rounded-xl border text-sm transition-all ${
                      language === l.id
                        ? "border-primary/40 bg-primary/8 text-primary"
                        : "border-border bg-card text-foreground hover:bg-muted/50"
                    }`}
                    style={{ fontWeight: language === l.id ? 500 : 400 }}
                  >
                    <Globe size={13} />
                    {l.label}
                  </button>
                ))}
              </div>
            </Section>

            {/* Notifications & sound */}
            <Section title="Notificaciones">
              <SettingRow icon={Bell} label="Notificaciones" desc="Avisos cuando el asistente responde">
                <Switch
                  checked={notifications}
                  onCheckedChange={onNotificationsChange}
                />
              </SettingRow>
              <SettingRow icon={sound ? Volume2 : VolumeX} label="Sonidos" desc="Efecto al recibir respuesta">
                <Switch
                  checked={sound}
                  onCheckedChange={onSoundChange}
                />
              </SettingRow>
            </Section>

            {/* Chat preferences */}
            <Section title="Chat">
              <SettingRow icon={MessageSquare} label="Historial" desc="Guardar conversaciones automáticamente">
                <Switch checked={true} onCheckedChange={() => {}} />
              </SettingRow>
              <SettingRow icon={Shield} label="Privacidad" desc="No usar mis chats para entrenamiento">
                <Switch checked={true} onCheckedChange={() => {}} />
              </SettingRow>
            </Section>

            <Separator className="mb-5 opacity-40" />

            {/* About */}
            <div className="flex items-center justify-between px-3 py-2.5 rounded-xl bg-card border border-border/60">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-xl bg-muted flex items-center justify-center">
                  <Info size={15} className="text-muted-foreground" />
                </div>
                <div>
                  <p className="text-sm text-foreground" style={{ fontWeight: 500 }}>Acerca del asistente</p>
                  <p className="text-xs text-muted-foreground">Versión 1.0.0</p>
                </div>
              </div>
              <ChevronRight size={15} className="text-muted-foreground" />
            </div>

          </div>
        </ScrollArea>
      </aside>
    </>
  );
}
