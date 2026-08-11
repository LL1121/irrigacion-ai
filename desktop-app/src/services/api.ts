import { getApiBaseUrl } from "./config";

export type ChatMessage = {
  role: "user" | "assistant" | string;
  message: string;
  created_at?: string | null;
  from_cache?: boolean;
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
): Promise<{ reply: string; from_cache: boolean; status: string }> {
  const res = await fetch(`${getApiBaseUrl()}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, message }),
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
