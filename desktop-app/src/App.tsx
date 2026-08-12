import { useCallback, useEffect, useState } from "react";
import { Sidebar } from "./components/Sidebar";
import { ChatWindow } from "./components/ChatWindow";
import { FileUploadModal } from "./components/FileUploadModal";
import { SettingsModal } from "./components/SettingsModal";
import {
  approveSkill,
  getSessionMessages,
  healthCheck,
  listSessions,
  sendChat,
  type ChatMessage,
  type SessionSummary,
} from "./services/api";

function newSessionId(): string {
  return crypto.randomUUID();
}

function App() {
  const [sessionId, setSessionId] = useState(newSessionId);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [approving, setApproving] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [apiOnline, setApiOnline] = useState(false);

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

  async function handleNewChat() {
    setSessionId(newSessionId());
    setMessages([]);
    setApproving(false);
  }

  async function handleSelectSession(id: string) {
    setSessionId(id);
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
    const userMsg: ChatMessage = { role: "user", message: text };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);
    try {
      const result = await sendChat(sessionId, text);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          message: result.reply,
          from_cache: result.from_cache,
          status: result.status,
          skill_name: result.skill_name,
          skill_description: result.skill_description,
        },
      ]);
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
        },
      ]);
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
        },
      ]);
    } finally {
      setApproving(false);
    }
  }

  return (
    <div className="flex h-full overflow-hidden">
      <Sidebar
        sessions={sessions}
        activeSessionId={sessionId}
        apiOnline={apiOnline}
        onNewChat={() => void handleNewChat()}
        onSelectSession={(id) => void handleSelectSession(id)}
        onOpenUpload={() => setUploadOpen(true)}
        onOpenSettings={() => setSettingsOpen(true)}
      />
      <ChatWindow
        messages={messages}
        loading={loading}
        approving={approving}
        onSend={handleSend}
        onApproveSkill={(approved) => void handleApproveSkill(approved)}
      />
      <FileUploadModal open={uploadOpen} onClose={() => setUploadOpen(false)} />
      <SettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onSaved={() => {
          void refreshHealth();
          void refreshSessions();
        }}
      />
    </div>
  );
}

export default App;
