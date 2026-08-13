import { getApiBaseUrl } from "./config";

export type SpeedMode = "fast" | "balanced" | "deep";

const AUTH_TOKEN_KEY = "irrigacion.authToken";

export type AuthUser = {
  id: string;
  email: string;
  name?: string | null;
  picture?: string | null;
};

export type ChatAttachment = {
  file_id: string;
  filename: string;
  mime: string;
  size_bytes?: number | null;
};

export type ChatMessage = {
  role: "user" | "assistant" | string;
  message: string;
  created_at?: string | null;
  id?: string;
  animate?: boolean;
  from_cache?: boolean;
  status?: string;
  skill_name?: string | null;
  skill_description?: string | null;
  attachments?: ChatAttachment[];
  approval_kind?: "download_remote" | "execute_local" | "google_tool" | string | null;
};

export type ChatResponse = {
  reply: string;
  from_cache: boolean;
  status: string;
  skill_name?: string | null;
  skill_description?: string | null;
  attachments?: ChatAttachment[] | null;
  approval_kind?: "download_remote" | "execute_local" | "google_tool" | string | null;
};

export type SkillApproveResponse = {
  reply: string;
  status: string;
  skill_name?: string | null;
  skill_description?: string | null;
  approved: boolean;
  attachments?: ChatAttachment[] | null;
  approval_kind?: "download_remote" | "execute_local" | "google_tool" | string | null;
  audit?: {
    is_safe?: boolean;
    risk_score?: number;
    reason?: string;
  } | null;
};

export type SessionSummary = {
  session_id: string;
  last_at: string | null;
  last_message: string | null;
};

export type UploadResult = {
  filename: string;
  chunks_created: number;
  error?: string;
  warning?: string;
};

export function getStoredAccessToken(): string | null {
  try {
    return localStorage.getItem(AUTH_TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setStoredAccessToken(token: string | null): void {
  try {
    if (!token) localStorage.removeItem(AUTH_TOKEN_KEY);
    else localStorage.setItem(AUTH_TOKEN_KEY, token);
  } catch {
    // storage puede fallar en modo privado
  }
}

function authHeaders(extra?: HeadersInit): HeadersInit {
  const token = getStoredAccessToken();
  const base: Record<string, string> = {};
  if (token) base.Authorization = `Bearer ${token}`;
  return { ...base, ...(extra as Record<string, string> | undefined) };
}

async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers || {});
  const token = getStoredAccessToken();
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  return fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });
}

async function parseError(res: Response): Promise<string> {
  try {
    const data = await res.json();
    if (typeof data?.detail === "string") return data.detail;
    return JSON.stringify(data);
  } catch {
    return res.statusText || `HTTP ${res.status}`;
  }
}

export async function fetchAuthMe(): Promise<{
  authenticated: boolean;
  user: AuthUser | null;
  google_oauth_configured?: boolean;
}> {
  const res = await apiFetch("/api/auth/me");
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function startGoogleLogin(): Promise<void> {
  const res = await apiFetch("/api/auth/google/start");
  if (!res.ok) throw new Error(await parseError(res));
  const data = (await res.json()) as { authorize_url?: string };
  if (!data.authorize_url) throw new Error("No se recibió URL de Google OAuth");
  window.location.href = data.authorize_url;
}

export async function logoutAuth(): Promise<void> {
  try {
    await apiFetch("/api/auth/logout", { method: "POST" });
  } finally {
    setStoredAccessToken(null);
  }
}

export async function sendChat(
  sessionId: string,
  message: string,
  speedMode: SpeedMode = "deep",
  signal?: AbortSignal,
): Promise<ChatResponse> {
  const res = await apiFetch("/api/chat", {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ session_id: sessionId, message, speed_mode: speedMode }),
    signal,
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function truncateSession(
  sessionId: string,
  fromCreatedAt: string,
): Promise<void> {
  const res = await apiFetch(`/api/sessions/${sessionId}/truncate`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ from_created_at: fromCreatedAt }),
  });
  if (!res.ok) throw new Error(await parseError(res));
}

export async function approveSkill(
  sessionId: string,
  approved: boolean,
): Promise<SkillApproveResponse> {
  const res = await apiFetch("/api/skills/approve", {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ session_id: sessionId, approved }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function uploadFiles(files: File[]): Promise<{
  processed: number;
  results: UploadResult[];
}> {
  const form = new FormData();
  for (const file of files) {
    form.append("files", file);
  }
  form.append("scope", "irrigacion");
  const res = await apiFetch("/api/upload", {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function listSessions(): Promise<SessionSummary[]> {
  const res = await apiFetch("/api/sessions");
  if (!res.ok) throw new Error(await parseError(res));
  const data = await res.json();
  return data.sessions ?? [];
}

export async function deleteSession(sessionId: string): Promise<void> {
  const res = await apiFetch(`/api/sessions/${sessionId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(await parseError(res));
}

export async function getSessionMessages(
  sessionId: string,
): Promise<ChatMessage[]> {
  const res = await apiFetch(`/api/sessions/${sessionId}/messages`);
  if (!res.ok) throw new Error(await parseError(res));
  const data = await res.json();
  return data.messages ?? [];
}

export async function healthCheck(): Promise<boolean> {
  try {
    const res = await fetch(`${getApiBaseUrl()}/health`);
    return res.ok;
  } catch {
    return false;
  }
}
