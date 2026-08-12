import { getApiBaseUrl } from "./config";

export type SpeedMode = "fast" | "balanced" | "deep";

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
  approval_kind?: "download_remote" | "execute_local" | string | null;
};

export type ChatResponse = {
  reply: string;
  from_cache: boolean;
  status: string;
  skill_name?: string | null;
  skill_description?: string | null;
  attachments?: ChatAttachment[] | null;
  approval_kind?: "download_remote" | "execute_local" | string | null;
};

export type SkillApproveResponse = {
  reply: string;
  status: string;
  skill_name?: string | null;
  skill_description?: string | null;
  approved: boolean;
  attachments?: ChatAttachment[] | null;
  approval_kind?: "download_remote" | "execute_local" | string | null;
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

async function parseError(res: Response): Promise<string> {
  try {
    const data = await res.json();
    if (typeof data?.detail === "string") return data.detail;
    return JSON.stringify(data);
  } catch {
    return res.statusText || `HTTP ${res.status}`;
  }
}

export async function sendChat(
  sessionId: string,
  message: string,
  speedMode: SpeedMode = "deep",
  signal?: AbortSignal,
): Promise<ChatResponse> {
  const res = await fetch(`${getApiBaseUrl()}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
  const res = await fetch(`${getApiBaseUrl()}/api/sessions/${sessionId}/truncate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ from_created_at: fromCreatedAt }),
  });
  if (!res.ok) throw new Error(await parseError(res));
}

export async function approveSkill(
  sessionId: string,
  approved: boolean,
): Promise<SkillApproveResponse> {
  const res = await fetch(`${getApiBaseUrl()}/api/skills/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
  const res = await fetch(`${getApiBaseUrl()}/api/upload`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function listSessions(): Promise<SessionSummary[]> {
  const res = await fetch(`${getApiBaseUrl()}/api/sessions`);
  if (!res.ok) throw new Error(await parseError(res));
  const data = await res.json();
  return data.sessions ?? [];
}

export async function getSessionMessages(
  sessionId: string,
): Promise<ChatMessage[]> {
  const res = await fetch(`${getApiBaseUrl()}/api/sessions/${sessionId}/messages`);
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
