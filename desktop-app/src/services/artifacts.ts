import { getApiBaseUrl } from "./config";

export type ChatAttachment = {
  file_id: string;
  filename: string;
  mime: string;
  size_bytes?: number | null;
  previewable?: boolean;
};

export type ArtifactInfo = ChatAttachment & {
  previewable: boolean;
};

export type ArtifactPreview =
  | ({ mode: "text"; content: string } & ArtifactInfo)
  | ({ mode: "binary" } & ArtifactInfo)
  | ({ mode: "unsupported" } & ArtifactInfo);

async function parseError(res: Response): Promise<string> {
  try {
    const data = await res.json();
    if (typeof data?.detail === "string") return data.detail;
    return JSON.stringify(data);
  } catch {
    return res.statusText || `HTTP ${res.status}`;
  }
}

export function artifactDownloadUrl(fileId: string): string {
  return `${getApiBaseUrl()}/api/documents/${fileId}`;
}

export async function fetchArtifactInfo(fileId: string): Promise<ArtifactInfo> {
  const res = await fetch(`${getApiBaseUrl()}/api/documents/${fileId}/info`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function fetchArtifactPreview(fileId: string): Promise<ArtifactPreview> {
  const res = await fetch(`${getApiBaseUrl()}/api/documents/${fileId}/preview`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function fetchArtifactBlob(fileId: string): Promise<Blob> {
  const res = await fetch(artifactDownloadUrl(fileId));
  if (!res.ok) throw new Error(await parseError(res));
  return res.blob();
}

/** Descarga silenciosa vía fetch + anchor programático (sin abrir pestañas). */
export async function downloadArtifact(fileId: string, filename: string): Promise<void> {
  const blob = await fetchArtifactBlob(fileId);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

export function formatFileSize(bytes?: number | null): string {
  if (!bytes || bytes <= 0) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function attachmentIconLabel(mime: string): string {
  if (mime.startsWith("image/")) return "Imagen";
  if (mime === "application/pdf") return "PDF";
  if (mime.includes("wordprocessingml")) return "Word";
  if (mime.startsWith("text/") || mime === "application/json") return "Texto";
  if (mime === "text/csv") return "CSV";
  return "Archivo";
}
