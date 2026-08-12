import { useState, useCallback } from "react";
import { ThemeProvider, useTheme } from "next-themes";
import { Menu, Settings, Moon, Sun, Sparkles } from "lucide-react";
import { Toaster } from "sonner";
import { ChatSidebar } from "./components/ChatSidebar";
import { ChatMessages } from "./components/ChatMessages";
import { ChatInput } from "./components/ChatInput";
import { SettingsPanel } from "./components/SettingsPanel";
import type { Conversation, ChatMessage, FileAttachment } from "./components/ChatSidebar";

// ─── Mock AI response pool ────────────────────────────────────────────────────
const AI_RESPONSES = [
  "¡Claro que sí! Con gusto te ayudo con eso. Dame un momento para analizar tu solicitud y prepararte la mejor respuesta posible.",
  "Entiendo perfectamente lo que necesitas. Aquí te explico paso a paso cómo podemos resolverlo juntos de la manera más sencilla.",
  "Excelente pregunta. Voy a darte una respuesta clara y detallada para que puedas entenderlo sin complicaciones.",
  "Por supuesto, este es un tema muy interesante. Te lo explico de forma sencilla: primero debemos entender el contexto, y luego podemos avanzar hacia la solución.",
  "Perfecto, he analizado tu mensaje. Aquí está mi respuesta:\n\nEsto es algo que puedo ayudarte a resolver completamente. El proceso tiene algunos pasos clave que debes seguir, y estoy aquí para guiarte en cada uno de ellos.",
  "¡Por supuesto! Es un placer ayudarte. Basándome en lo que me comentas, te recomiendo lo siguiente:\n\n1. Primero, considera el contexto general de tu situación.\n2. Luego, evalúa las opciones disponibles.\n3. Finalmente, toma una decisión informada.\n\n¿Te gustaría que profundizara en alguno de estos puntos?",
  "Entendido. He revisado tu consulta y tengo varias ideas que podrían ayudarte. La clave aquí es encontrar el enfoque correcto para tu situación específica.",
  "Eso es algo que puedo explicarte muy bien. En esencia, el concepto funciona así: partes de una base sólida y vas construyendo gradualmente hasta llegar al resultado que buscas.",
];

function getAIResponse(userMessage: string): string {
  const lower = userMessage.toLowerCase();
  if (lower.includes("correo") || lower.includes("email"))
    return "Con gusto te ayudo a redactar ese correo. Para hacerlo efectivo, necesito saber: ¿cuál es el tono que buscas (formal o informal)?, ¿quién es el destinatario?, y ¿cuál es el mensaje principal que deseas transmitir? Con esa información puedo preparar una versión inicial para ti.";
  if (lower.includes("translate") || lower.includes("traduc"))
    return "¡Perfecto! Puedo ayudarte con esa traducción. Para asegurar que quede natural y precisa, envíame el texto que deseas traducir y especifica si necesitas un estilo formal o informal.";
  if (lower.includes("código") || lower.includes("programar") || lower.includes("error"))
    return "Entendido. Voy a revisar ese problema de código contigo. Comparte el fragmento específico que te está dando problemas y dime qué error ves o qué resultado esperas. Así puedo darte una solución precisa.";
  if (lower.includes("idea") || lower.includes("negocio") || lower.includes("proyecto"))
    return "¡Me encanta ese tipo de preguntas creativas! Aquí van algunas ideas iniciales:\n\n• Enfócate primero en identificar un problema real que experimentes tú mismo.\n• Considera el mercado local antes de escalar.\n• Empieza pequeño y valida antes de invertir mucho.\n\n¿Quieres que profundice en alguna dirección específica?";
  if (lower.includes("explicar") || lower.includes("explica") || lower.includes("qué es"))
    return "Por supuesto, te lo explico de manera sencilla. Este tema tiene varias capas, pero vamos a ir de lo más básico a lo más avanzado. Primero, lo fundamental es entender el concepto central... ¿Hay algún aspecto en particular que quieras que explique primero?";
  const i = Math.floor(Math.random() * AI_RESPONSES.length);
  return AI_RESPONSES[i];
}

// ─── Mock history data ────────────────────────────────────────────────────────
function generateMockHistory(): Conversation[] {
  const now = new Date();
  const h = (hoursAgo: number): Date => new Date(now.getTime() - hoursAgo * 3600000);

  return [
    {
      id: "c1",
      title: "Ayuda con correo a cliente",
      preview: "¿Puedes redactar un correo formal para presentar...",
      timestamp: h(1),
      messages: [
        {
          id: "m1",
          role: "user",
          content: "Necesito redactar un correo para presentar mi servicio de diseño a una empresa grande. ¿Me ayudas?",
          timestamp: h(1),
        },
        {
          id: "m2",
          role: "assistant",
          content:
            "¡Con gusto te ayudo! Para redactar un correo efectivo de presentación de servicios, aquí tienes una estructura que funciona muy bien:\n\nAsunto: Propuesta de servicios de diseño – [Tu nombre/empresa]\n\nEstimado/a [nombre]:\n\nMi nombre es [tu nombre] y me especializo en diseño gráfico y comunicación visual. He tenido la oportunidad de conocer el trabajo de [empresa] y creo que puedo aportar valor significativo a sus proyectos.\n\n¿Te gustaría que complete los datos específicos de tu caso?",
          timestamp: new Date(h(1).getTime() + 30000),
        },
      ],
    },
    {
      id: "c2",
      title: "Explicación sobre inteligencia artificial",
      preview: "La IA es un campo de la informática que...",
      timestamp: h(3),
      messages: [
        {
          id: "m3",
          role: "user",
          content: "¿Puedes explicarme qué es la inteligencia artificial de forma sencilla?",
          timestamp: h(3),
        },
        {
          id: "m4",
          role: "assistant",
          content:
            "¡Por supuesto! Te lo explico de manera muy sencilla:\n\nLa inteligencia artificial (IA) es como enseñarle a una computadora a 'pensar' y aprender, similar a como lo hacen las personas.\n\nImagina que tienes un niño que nunca ha visto un gato. Le muestras miles de fotos de gatos y le dices 'esto es un gato'. Con el tiempo, el niño aprende a reconocer gatos por sí solo. Así funciona la IA.\n\nEn la práctica, esto nos permite tener asistentes como yo que pueden responder preguntas, traducir textos, analizar documentos y mucho más.\n\n¿Hay algún aspecto de la IA que te gustaría conocer mejor?",
          timestamp: new Date(h(3).getTime() + 45000),
        },
      ],
    },
    {
      id: "c3",
      title: "Ideas para negocio de repostería",
      preview: "Aquí van algunas ideas para comenzar...",
      timestamp: h(26),
      messages: [
        {
          id: "m5",
          role: "user",
          content: "Quiero empezar un negocio de repostería en casa. ¿Qué ideas tienes?",
          timestamp: h(26),
        },
        {
          id: "m6",
          role: "assistant",
          content:
            "¡Qué buena idea! La repostería en casa tiene mucho potencial. Aquí te doy algunas estrategias para comenzar:\n\n1. **Especialización**: Elige un nicho (pasteles de cumpleaños, macarons, sin gluten, etc.)\n2. **Redes sociales**: Instagram y TikTok son perfectos para mostrar tus creaciones\n3. **Pedidos personalizados**: Empieza con encargos para conocidos y familiares\n4. **Precios justos**: Calcula bien los costos de ingredientes + tiempo + ganancia\n5. **Packaging**: Una presentación bonita hace la diferencia\n\n¿En qué tipo de repostería te gustaría especializarte?",
          timestamp: new Date(h(26).getTime() + 60000),
        },
      ],
    },
    {
      id: "c4",
      title: "Traducción de propuesta comercial",
      preview: "He traducido tu documento al inglés manteniendo...",
      timestamp: h(50),
      messages: [
        {
          id: "m7",
          role: "user",
          content: "Necesito traducir mi propuesta comercial al inglés. El documento tiene 3 páginas.",
          timestamp: h(50),
        },
        {
          id: "m8",
          role: "assistant",
          content:
            "Claro, puedo ayudarte con esa traducción. Para hacer un trabajo de calidad, te recomiendo que me envíes el texto directamente en el chat o adjuntes el documento.\n\nAlgunas cosas que debo saber:\n• ¿El inglés es para EE.UU., Reino Unido u otro mercado?\n• ¿El tono debe ser formal o más cercano?\n• ¿Hay términos técnicos específicos de tu industria?\n\nCuando tengas el texto listo, ¡empezamos!",
          timestamp: new Date(h(50).getTime() + 30000),
        },
      ],
    },
    {
      id: "c5",
      title: "Plan de alimentación saludable",
      preview: "Aquí tienes un plan de 7 días balanceado...",
      timestamp: h(120),
      messages: [
        {
          id: "m9",
          role: "user",
          content: "¿Puedes ayudarme a crear un plan de alimentación saludable para la semana?",
          timestamp: h(120),
        },
        {
          id: "m10",
          role: "assistant",
          content:
            "¡Con gusto! Aquí tienes un plan básico de 7 días:\n\n**Lunes – Viernes (días laborales):**\n• Desayuno: Avena con frutas y nueces\n• Almuerzo: Proteína + vegetales + carbohidrato complejo\n• Cena: Sopa o ensalada con proteína ligera\n\n**Fin de semana:**\n• Un poco más flexible, pero manteniendo el balance\n\nPara personalizar mejor este plan, cuéntame: ¿tienes alguna restricción alimentaria? ¿cuántas personas son? ¿cuál es tu objetivo (perder peso, ganar energía, etc.)?",
          timestamp: new Date(h(120).getTime() + 90000),
        },
      ],
    },
  ];
}

// ─── Inner App (needs ThemeProvider) ─────────────────────────────────────────
function ChatApp() {
  const { theme, setTheme, resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";

  const [conversations, setConversations] = useState<Conversation[]>(generateMockHistory);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [isTyping, setIsTyping] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);

  // Settings state
  const [model, setModel] = useState("gpt-4o-mini");
  const [sound, setSound] = useState(true);
  const [notifications, setNotifications] = useState(true);
  const [language, setLanguage] = useState("es");

  const activeConversation = conversations.find((c) => c.id === activeId) ?? null;
  const messages = activeConversation?.messages ?? [];

  const createNewConversation = useCallback(() => {
    setActiveId(null);
    setSidebarOpen(false);
  }, []);

  const selectConversation = useCallback((id: string) => {
    setActiveId(id);
    setSidebarOpen(false);
  }, []);

  const deleteConversation = useCallback((id: string) => {
    setConversations((prev) => prev.filter((c) => c.id !== id));
    if (activeId === id) setActiveId(null);
  }, [activeId]);

  const handleSend = useCallback(
    async (content: string, attachments: FileAttachment[]) => {
      if (!content.trim() && attachments.length === 0) return;

      const userMsg: ChatMessage = {
        id: `u-${Date.now()}`,
        role: "user",
        content,
        timestamp: new Date(),
        attachments: attachments.length > 0 ? attachments : undefined,
      };

      let targetId = activeId;
      const existingConv = conversations.find((c) => c.id === targetId);

      if (!targetId || !existingConv) {
        const title =
          content.slice(0, 42) || (attachments[0] ? attachments[0].name : "Nueva conversación");
        targetId = `c-${Date.now()}`;
        const newConv: Conversation = {
          id: targetId,
          title: content.length > 42 ? title + "..." : title,
          preview: content || `[${attachments.length} archivo(s)]`,
          timestamp: new Date(),
          messages: [userMsg],
        };
        setActiveId(targetId);
        setConversations((prev) => [newConv, ...prev]);
      } else {
        setConversations((prev) =>
          prev.map((c) =>
            c.id === targetId
              ? {
                  ...c,
                  messages: [...c.messages, userMsg],
                  preview: content || `[${attachments.length} archivo(s)]`,
                  timestamp: new Date(),
                }
              : c
          )
        );
      }

      setIsTyping(true);

      const delay = 1200 + Math.random() * 1200;
      await new Promise((r) => setTimeout(r, delay));

      const aiResponse = getAIResponse(content);
      const aiMsg: ChatMessage = {
        id: `a-${Date.now()}`,
        role: "assistant",
        content: aiResponse,
        timestamp: new Date(),
      };

      setIsTyping(false);
      setConversations((prev) =>
        prev.map((c) =>
          c.id === targetId
            ? { ...c, messages: [...c.messages, aiMsg], timestamp: new Date() }
            : c
        )
      );
    },
    [activeId, conversations]
  );

  const handleThemeChange = (t: "light" | "dark" | "system") => {
    setTheme(t);
  };

  const currentTheme = (theme as "light" | "dark" | "system") ?? "system";

  return (
    <div className="h-screen w-screen flex overflow-hidden bg-background">
      {/* Sidebar */}
      <ChatSidebar
        conversations={conversations}
        activeId={activeId}
        onSelect={selectConversation}
        onNew={createNewConversation}
        onDelete={deleteConversation}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />

      {/* Main */}
      <main className="flex-1 flex flex-col min-w-0 relative">
        {/* Header */}
        <header className="flex items-center justify-between px-4 py-3 border-b border-border bg-background/80 backdrop-blur-sm shrink-0">
          <div className="flex items-center gap-3">
            <button
              className="lg:hidden w-8 h-8 rounded-xl flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-all"
              onClick={() => setSidebarOpen(true)}
            >
              <Menu size={18} />
            </button>

            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-xl bg-primary/15 flex items-center justify-center">
                <Sparkles size={14} className="text-primary" />
              </div>
              <div className="hidden sm:block">
                <p className="text-sm text-foreground leading-none" style={{ fontWeight: 600 }}>
                  {activeConversation ? activeConversation.title : "Asistente IA"}
                </p>
                <p className="text-[10px] text-muted-foreground mt-0.5">
                  {isTyping ? "Escribiendo..." : "En línea"}
                </p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Theme toggle */}
            <button
              onClick={() => setTheme(isDark ? "light" : "dark")}
              className="w-8 h-8 rounded-xl flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-all"
              title={isDark ? "Modo día" : "Modo noche"}
            >
              {isDark ? <Sun size={16} /> : <Moon size={16} />}
            </button>

            {/* Settings */}
            <button
              onClick={() => setSettingsOpen(true)}
              className="w-8 h-8 rounded-xl flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-all"
              title="Configuración"
            >
              <Settings size={16} />
            </button>
          </div>
        </header>

        {/* Messages */}
        <ChatMessages
          messages={messages}
          isTyping={isTyping}
          onSuggestedPrompt={(prompt) => handleSend(prompt, [])}
        />

        {/* Input */}
        <ChatInput onSend={handleSend} disabled={isTyping} />
      </main>

      {/* Settings panel */}
      <SettingsPanel
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        theme={currentTheme}
        onThemeChange={handleThemeChange}
        model={model}
        onModelChange={setModel}
        sound={sound}
        onSoundChange={setSound}
        notifications={notifications}
        onNotificationsChange={setNotifications}
        language={language}
        onLanguageChange={setLanguage}
      />

      <Toaster position="bottom-right" richColors />
    </div>
  );
}

// ─── Root with ThemeProvider ──────────────────────────────────────────────────
export default function App() {
  return (
    <ThemeProvider attribute="class" defaultTheme="light" enableSystem>
      <ChatApp />
    </ThemeProvider>
  );
}
