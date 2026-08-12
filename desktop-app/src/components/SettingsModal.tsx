import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import {
  Bell,
  BellOff,
  Clock,
  Info,
  Monitor,
  Moon,
  Power,
  Sun,
  Type,
  Volume2,
  VolumeX,
  X,
} from "lucide-react";
import { getApiBaseUrl, isSameOriginDeployment, LAN_API_BASE, setApiBaseUrl } from "../services/config";
import { healthCheck } from "../services/api";
import { useTheme } from "../theme";
import { isTauriRuntime } from "../native";

type SettingsModalProps = {
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
  soundEnabled: boolean;
  onSoundEnabledChange: (enabled: boolean) => void;
  notificationsEnabled: boolean;
  onNotificationsEnabledChange: (enabled: boolean) => void;
  autostartEnabled: boolean;
  onAutostartEnabledChange: (enabled: boolean) => void;
  fontScale: number;
  onFontScaleChange: (scale: number) => void;
  showTimestamps: boolean;
  onShowTimestampsChange: (enabled: boolean) => void;
};

const THEMES = [
  { id: "light" as const, icon: Sun, label: "Día" },
  { id: "dark" as const, icon: Moon, label: "Noche" },
  { id: "system" as const, icon: Monitor, label: "Sistema" },
];

const FONT_SCALES = [
  { value: 0.9, label: "Pequeño" },
  { value: 1, label: "Cómodo" },
  { value: 1.125, label: "Grande" },
];

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mb-6">
      <p className="mb-3 px-1 text-[11px] font-medium uppercase tracking-wider text-muted-foreground/70">
        {title}
      </p>
      <div className="flex flex-col gap-2">{children}</div>
    </div>
  );
}

function Switch({
  checked,
  onCheckedChange,
  disabled,
}: {
  checked: boolean;
  onCheckedChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onCheckedChange(!checked)}
      className={`inline-flex h-[1.15rem] w-8 shrink-0 items-center rounded-full border border-transparent transition-all disabled:cursor-not-allowed disabled:opacity-40 ${
        checked ? "bg-primary" : "bg-switch-background"
      }`}
    >
      <span
        className={`block size-4 rounded-full bg-card shadow transition-transform ${
          checked ? "translate-x-[calc(100%-2px)]" : "translate-x-0"
        }`}
      />
    </button>
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
  children?: ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-xl border border-border/60 bg-card px-3 py-2.5">
      <div className="flex items-center gap-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-muted">
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

export function SettingsModal({
  open,
  onClose,
  onSaved,
  soundEnabled,
  onSoundEnabledChange,
  notificationsEnabled,
  onNotificationsEnabledChange,
  autostartEnabled,
  onAutostartEnabledChange,
  fontScale,
  onFontScaleChange,
  showTimestamps,
  onShowTimestampsChange,
}: SettingsModalProps) {
  const { theme, setTheme } = useTheme();
  const [url, setUrl] = useState(getApiBaseUrl);
  const [testing, setTesting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const desktopFeatures = isTauriRuntime();

  useEffect(() => {
    if (open) {
      setUrl(getApiBaseUrl());
      setMessage(null);
    }
  }, [open]);

  async function handleSave(event: FormEvent) {
    event.preventDefault();
    setApiBaseUrl(url);
    setTesting(true);
    setMessage(null);
    try {
      const ok = await healthCheck();
      setMessage(
        ok
          ? "Guardado. API alcanzable."
          : "Guardado, pero no se pudo conectar. Revisá la URL / firewall.",
      );
      onSaved();
    } finally {
      setTesting(false);
    }
  }

  return (
    <>
      {open && (
        <div
          className="fixed inset-0 z-40 bg-black/20 backdrop-blur-sm"
          onClick={onClose}
        />
      )}

      <aside
        className={`fixed right-0 top-0 z-50 flex h-full w-full max-w-sm flex-col border-l border-border bg-background shadow-2xl transition-transform duration-300 ease-in-out ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between border-b border-border px-5 pb-4 pt-5">
          <div>
            <h2 className="text-foreground" style={{ fontWeight: 600, fontSize: "1rem" }}>
              Configuración
            </h2>
            <p className="mt-0.5 text-xs text-muted-foreground">Personalizá tu experiencia</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-xl text-muted-foreground transition-all hover:bg-muted hover:text-foreground"
          >
            <X size={16} />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="px-4 py-5">
            <Section title="Apariencia">
              <div className="flex gap-2 rounded-2xl bg-muted p-1">
                {THEMES.map(({ id, icon: Icon, label }) => (
                  <button
                    key={id}
                    type="button"
                    onClick={() => setTheme(id)}
                    className={`flex flex-1 flex-col items-center gap-1.5 rounded-xl py-3 text-xs transition-all duration-200 ${
                      theme === id
                        ? "border border-border bg-card text-primary shadow-sm"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                    style={{ fontWeight: theme === id ? 500 : 400 }}
                  >
                    <Icon size={16} />
                    {label}
                  </button>
                ))}
              </div>

              <div className="mt-2 flex gap-2 rounded-2xl bg-muted p-1">
                {FONT_SCALES.map(({ value, label }) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => onFontScaleChange(value)}
                    className={`flex flex-1 flex-col items-center gap-1.5 rounded-xl py-3 text-xs transition-all duration-200 ${
                      fontScale === value
                        ? "border border-border bg-card text-primary shadow-sm"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                    style={{ fontWeight: fontScale === value ? 500 : 400 }}
                  >
                    <Type size={value === 0.9 ? 13 : value === 1.125 ? 18 : 15} />
                    {label}
                  </button>
                ))}
              </div>
            </Section>

            <Section title="Servidor">
              {isSameOriginDeployment() && !desktopFeatures ? (
                <p className="rounded-xl border border-primary/20 bg-primary/5 px-3 py-2.5 text-xs leading-relaxed text-muted-foreground">
                  La PWA detectó la API en el mismo servidor (
                  <span className="font-mono text-primary">{getApiBaseUrl()}</span>
                  ). No hace falta configurar la URL manualmente.
                </p>
              ) : (
              <form onSubmit={handleSave} className="space-y-3">
                <label className="block space-y-1.5">
                  <span className="text-xs font-medium text-muted-foreground">API base URL</span>
                  <input
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    placeholder="http://100.68.57.77:8000"
                    className="w-full rounded-xl border border-border bg-input-background px-3 py-2 font-mono text-sm text-foreground outline-none focus:border-primary/50"
                  />
                </label>
                <p className="text-[11px] leading-relaxed text-muted-foreground">
                  Default vía Tailscale:{" "}
                  <span className="font-mono text-primary">http://100.68.57.77:8000</span>. En la
                  LAN de oficina también sirve{" "}
                  <span className="font-mono text-primary">{LAN_API_BASE}</span>.
                </p>
                {message && (
                  <p className="rounded-xl border border-border bg-card px-3 py-2 text-xs text-foreground">
                    {message}
                  </p>
                )}
                <button
                  type="submit"
                  disabled={testing || !url.trim()}
                  className="w-full rounded-xl bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-40"
                >
                  {testing ? "Probando…" : "Guardar"}
                </button>
              </form>
              )}
            </Section>

            <Section title="Chat">
              <SettingRow icon={Clock} label="Mostrar hora" desc="Hora de envío en cada mensaje">
                <Switch checked={showTimestamps} onCheckedChange={onShowTimestampsChange} />
              </SettingRow>
              <SettingRow
                icon={soundEnabled ? Volume2 : VolumeX}
                label="Sonido"
                desc="Aviso sonoro al recibir respuesta"
              >
                <Switch checked={soundEnabled} onCheckedChange={onSoundEnabledChange} />
              </SettingRow>
              <SettingRow
                icon={notificationsEnabled ? Bell : BellOff}
                label="Notificaciones del sistema"
                desc={
                  desktopFeatures
                    ? "Avisar cuando llega una respuesta y la ventana no está en foco"
                    : "Disponible solo en la app de escritorio instalada"
                }
              >
                <Switch
                  checked={notificationsEnabled}
                  onCheckedChange={onNotificationsEnabledChange}
                  disabled={!desktopFeatures}
                />
              </SettingRow>
            </Section>

            <Section title="Sistema">
              <SettingRow
                icon={Power}
                label="Iniciar con el sistema"
                desc={
                  desktopFeatures
                    ? "Abrir Irrigación Bot al encender la computadora"
                    : "Disponible solo en la app de escritorio instalada"
                }
              >
                <Switch
                  checked={autostartEnabled}
                  onCheckedChange={onAutostartEnabledChange}
                  disabled={!desktopFeatures}
                />
              </SettingRow>
            </Section>

            <div className="mb-5 h-px bg-border/40" />

            <div className="flex items-center justify-between rounded-xl border border-border/60 bg-card px-3 py-2.5">
              <div className="flex items-center gap-3">
                <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-muted">
                  <Info size={15} className="text-muted-foreground" />
                </div>
                <div>
                  <p className="text-sm text-foreground" style={{ fontWeight: 500 }}>
                    Acerca de
                  </p>
                  <p className="text-xs text-muted-foreground">Irrigación Bot · Malargüe</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
