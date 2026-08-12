import { useCallback, useEffect, useState } from "react";
import { Sidebar } from "./components/Sidebar";
import { ChatWindow } from "./components/ChatWindow";
import { FileUploadModal } from "./components/FileUploadModal";
import { SettingsModal } from "./components/SettingsModal";
import { ThemeProvider } from "./theme";
import {
  ensureNotificationPermission,
  getAutostartEnabled,
  notifyDesktop,
  setAutostartEnabled as applyAutostartEnabled,
} from "./native";
import {
  approveSkill,
  getSessionMessages,
  healthCheck,
  listSessions,
  sendChat,
  type ChatMessage,
  type SessionSummary,
  type SpeedMode,
} from "./services/api";
import { newUuid } from "./utils/uuid";

const SOUND_STORAGE_KEY = "irrigacion.sound";
const NOTIFICATIONS_STORAGE_KEY = "irrigacion.notifications";
const FONT_SCALE_STORAGE_KEY = "irrigacion.fontScale";
const SHOW_TIMESTAMPS_STORAGE_KEY = "irrigacion.showTimestamps";
const SPEED_MODE_STORAGE_KEY = "irrigacion.speedMode";

function readSpeedMode(): SpeedMode {
  const stored = localStorage.getItem(SPEED_MODE_STORAGE_KEY);
  return stored === "fast" || stored === "balanced" || stored === "deep"
    ? stored
    : "deep";
}

function newSessionId(): string {
  return newUuid();
}

function readBoolPreference(key: string, fallback: boolean): boolean {
  const stored = localStorage.getItem(key);
  return stored === null ? fallback : stored === "true";
}

function readFontScale(): number {
  const stored = Number(localStorage.getItem(FONT_SCALE_STORAGE_KEY));
  return stored === 0.9 || stored === 1 || stored === 1.125 ? stored : 1;
}

function playNotificationSound() {
  try {
    const ctx = new AudioContext();
    const oscillator = ctx.createOscillator();
    const gain = ctx.createGain();
    oscillator.type = "sine";
    oscillator.frequency.value = 720;
    gain.gain.setValueAtTime(0.08, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.25);
    oscillator.connect(gain);
    gain.connect(ctx.destination);
    oscillator.start();
    oscillator.stop(ctx.currentTime + 0.25);
    oscillator.onended = () => void ctx.close();
  } catch {
    // El navegador puede bloquear el audio sin interacción previa; no es crítico.
  }
}

function truncate(text: string, max = 120): string {
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

function AppShell() {
  const [sessionId, setSessionId] = useState(newSessionId);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [approving, setApproving] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [apiOnline, setApiOnline] = useState(false);
  const [soundEnabled, setSoundEnabled] = useState(() =>
    readBoolPreference(SOUND_STORAGE_KEY, true),
  );
  const [notificationsEnabled, setNotificationsEnabled] = useState(() =>
    readBoolPreference(NOTIFICATIONS_STORAGE_KEY, false),
  );
  const [autostartEnabled, setAutostartEnabledState] = useState(false);
  const [fontScale, setFontScale] = useState(readFontScale);
  const [showTimestamps, setShowTimestamps] = useState(() =>
    readBoolPreference(SHOW_TIMESTAMPS_STORAGE_KEY, true),
  );
  const [speedMode, setSpeedMode] = useState<SpeedMode>(readSpeedMode);
  const [windowFocused, setWindowFocused] = useState(true);

  const refreshSessions = useCallback(async () => {
    try {
      const items = await listSessions();
      setSessions(items);
    } catch {
      // La API puede estar caída al inicio
    }
  }, []);

  const refreshHealth = useCallback(async () => {
    setApiOnline(await healthCheck());
  }, []);

  useEffect(() => {
    void (async () => {
      await refreshHealth();
      await refreshSessions();
    })();
    const timer = window.setInterval(() => {
      void refreshHealth();
    }, 15000);
    return () => window.clearInterval(timer);
  }, [refreshSessions, refreshHealth]);

  useEffect(() => {
    const onFocus = () => setWindowFocused(true);
    const onBlur = () => setWindowFocused(false);
    window.addEventListener("focus", onFocus);
    window.addEventListener("blur", onBlur);
    return () => {
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("blur", onBlur);
    };
  }, []);

  useEffect(() => {
    void getAutostartEnabled().then(setAutostartEnabledState);
  }, []);

  useEffect(() => {
    document.documentElement.style.setProperty("--font-scale", String(fontScale));
  }, [fontScale]);

  function notifyIfNeeded(body: string) {
    if (soundEnabled) playNotificationSound();
    if (notificationsEnabled && !windowFocused) {
      notifyDesktop("Irrigación Bot", truncate(body));
    }
  }

  function handleSoundEnabledChange(enabled: boolean) {
    setSoundEnabled(enabled);
    localStorage.setItem(SOUND_STORAGE_KEY, String(enabled));
  }

  async function handleNotificationsEnabledChange(enabled: boolean) {
    if (!enabled) {
      setNotificationsEnabled(false);
      localStorage.setItem(NOTIFICATIONS_STORAGE_KEY, "false");
      return;
    }
    const granted = await ensureNotificationPermission();
    setNotificationsEnabled(granted);
    localStorage.setItem(NOTIFICATIONS_STORAGE_KEY, String(granted));
  }

  async function handleAutostartEnabledChange(enabled: boolean) {
    await applyAutostartEnabled(enabled);
    setAutostartEnabledState(await getAutostartEnabled());
  }

  function handleFontScaleChange(scale: number) {
    setFontScale(scale);
    localStorage.setItem(FONT_SCALE_STORAGE_KEY, String(scale));
  }

  function handleShowTimestampsChange(enabled: boolean) {
    setShowTimestamps(enabled);
    localStorage.setItem(SHOW_TIMESTAMPS_STORAGE_KEY, String(enabled));
  }

  function handleSpeedModeChange(mode: SpeedMode) {
    setSpeedMode(mode);
    localStorage.setItem(SPEED_MODE_STORAGE_KEY, mode);
  }

  async function handleNewChat() {
    setSessionId(newSessionId());
    setMessages([]);
    setApproving(false);
    setSidebarOpen(false);
  }

  async function handleSelectSession(id: string) {
    setSessionId(id);
    setSidebarOpen(false);
    setLoading(true);
    try {
      const history = await getSessionMessages(id);
      setMessages(history);
    } catch (err) {
      setMessages([
        {
          role: "assistant",
          message:
            err instanceof Error
              ? `No se pudo cargar el historial: ${err.message}`
              : "No se pudo cargar el historial.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  async function handleSend(text: string) {
    const userMsg: ChatMessage = {
      role: "user",
      message: text,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);
    try {
      const result = await sendChat(sessionId, text, speedMode);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          message: result.reply,
          from_cache: result.from_cache,
          status: result.status,
          skill_name: result.skill_name,
          skill_description: result.skill_description,
          created_at: new Date().toISOString(),
        },
      ]);
      notifyIfNeeded(result.reply);
      await refreshSessions();
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          message:
            err instanceof Error
              ? `Error al consultar el agente: ${err.message}`
              : "Error al consultar el agente.",
          created_at: new Date().toISOString(),
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  async function handleApproveSkill(approved: boolean) {
    setApproving(true);
    try {
      const result = await approveSkill(sessionId, approved);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          message: result.reply,
          created_at: new Date().toISOString(),
        },
      ]);
      notifyIfNeeded(result.reply);
      await refreshSessions();
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          message:
            err instanceof Error
              ? `Error al resolver la skill: ${err.message}`
              : "Error al resolver la skill.",
          created_at: new Date().toISOString(),
        },
      ]);
    } finally {
      setApproving(false);
    }
  }

  return (
    <div className="flex h-dvh overflow-hidden bg-background text-foreground">
      <Sidebar
        sessions={sessions}
        activeSessionId={sessionId}
        apiOnline={apiOnline}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onNewChat={() => void handleNewChat()}
        onSelectSession={(id) => void handleSelectSession(id)}
      />
      <ChatWindow
        messages={messages}
        loading={loading}
        approving={approving}
        apiOnline={apiOnline}
        showTimestamps={showTimestamps}
        speedMode={speedMode}
        onSpeedModeChange={handleSpeedModeChange}
        onSend={handleSend}
        onApproveSkill={(approved) => void handleApproveSkill(approved)}
        onOpenSettings={() => setSettingsOpen(true)}
        onOpenUpload={() => setUploadOpen(true)}
        onOpenSidebar={() => setSidebarOpen(true)}
      />
      <FileUploadModal open={uploadOpen} onClose={() => setUploadOpen(false)} />
      <SettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onSaved={() => {
          void refreshHealth();
          void refreshSessions();
        }}
        soundEnabled={soundEnabled}
        onSoundEnabledChange={handleSoundEnabledChange}
        notificationsEnabled={notificationsEnabled}
        onNotificationsEnabledChange={(v) => void handleNotificationsEnabledChange(v)}
        autostartEnabled={autostartEnabled}
        onAutostartEnabledChange={(v) => void handleAutostartEnabledChange(v)}
        fontScale={fontScale}
        onFontScaleChange={handleFontScaleChange}
        showTimestamps={showTimestamps}
        onShowTimestampsChange={handleShowTimestampsChange}
      />
    </div>
  );
}

function App() {
  return (
    <ThemeProvider>
      <AppShell />
    </ThemeProvider>
  );
}

export default App;
