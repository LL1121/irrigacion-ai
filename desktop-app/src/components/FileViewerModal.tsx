import { useEffect, useState } from "react";
import { Download, FileText, LoaderCircle, X } from "lucide-react";
import {
  attachmentIconLabel,
  downloadArtifact,
  fetchArtifactBlob,
  fetchArtifactPreview,
  formatFileSize,
  type ArtifactPreview,
  type ChatAttachment,
} from "../services/artifacts";

type FileViewerModalProps = {
  attachment: ChatAttachment;
  open: boolean;
  onClose: () => void;
};

export function FileViewerModal({ attachment, open, onClose }: FileViewerModalProps) {
  const [preview, setPreview] = useState<ArtifactPreview | null>(null);
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    let objectUrl: string | null = null;

    async function load() {
      setLoading(true);
      setError(null);
      setPreview(null);
      setBlobUrl(null);
      try {
        const data = await fetchArtifactPreview(attachment.file_id);
        if (cancelled) return;
        setPreview(data);
        if (data.mode === "binary") {
          const blob = await fetchArtifactBlob(attachment.file_id);
          if (cancelled) return;
          objectUrl = URL.createObjectURL(blob);
          setBlobUrl(objectUrl);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "No se pudo cargar el archivo.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [open, attachment.file_id]);

  if (!open) return null;

  async function handleDownload() {
    setDownloading(true);
    try {
      await downloadArtifact(attachment.file_id, attachment.filename);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al descargar.");
    } finally {
      setDownloading(false);
    }
  }

  const mime = preview?.mime ?? attachment.mime;
  const size = formatFileSize(preview?.size_bytes ?? attachment.size_bytes);

  return (
    <>
      <div
        className="fixed inset-0 z-[60] bg-black/40 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="fixed inset-x-3 top-[5vh] z-[70] mx-auto flex max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden rounded-3xl border border-border bg-background shadow-2xl sm:inset-x-auto">
        <header className="flex shrink-0 items-center justify-between gap-3 border-b border-border px-4 py-3 sm:px-5">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-primary/15">
              <FileText size={18} className="text-primary" />
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-foreground">
                {attachment.filename}
              </p>
              <p className="text-xs text-muted-foreground">
                {attachmentIconLabel(mime)}
                {size ? ` · ${size}` : ""}
              </p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <button
              type="button"
              onClick={() => void handleDownload()}
              disabled={downloading}
              className="inline-flex items-center gap-1.5 rounded-xl bg-primary px-3 py-2 text-xs font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-40"
            >
              {downloading ? (
                <LoaderCircle size={14} className="animate-spin" />
              ) : (
                <Download size={14} />
              )}
              Descargar
            </button>
            <button
              type="button"
              onClick={onClose}
              className="flex h-9 w-9 items-center justify-center rounded-xl text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              <X size={16} />
            </button>
          </div>
        </header>

        <div className="min-h-0 flex-1 overflow-auto bg-muted/30 p-4 sm:p-5">
          {loading && (
            <div className="flex h-48 items-center justify-center">
              <LoaderCircle className="animate-spin text-primary" size={28} />
            </div>
          )}
          {error && (
            <p className="rounded-2xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
              {error}
            </p>
          )}
          {!loading && !error && preview?.mode === "text" && (
            <pre className="whitespace-pre-wrap rounded-2xl border border-border bg-card p-4 text-sm leading-relaxed text-foreground">
              {preview.content}
            </pre>
          )}
          {!loading && !error && preview?.mode === "binary" && blobUrl && mime.startsWith("image/") && (
            <div className="flex justify-center">
              <img
                src={blobUrl}
                alt={attachment.filename}
                className="max-h-[65vh] max-w-full rounded-2xl border border-border bg-card object-contain shadow-sm"
              />
            </div>
          )}
          {!loading && !error && preview?.mode === "binary" && blobUrl && mime === "application/pdf" && (
            <iframe
              src={blobUrl}
              title={attachment.filename}
              className="h-[65vh] w-full rounded-2xl border border-border bg-card shadow-sm"
            />
          )}
          {!loading && !error && preview?.mode === "unsupported" && (
            <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
              <FileText size={40} className="text-muted-foreground/40" />
              <p className="max-w-sm text-sm text-muted-foreground">
                No hay vista previa para este tipo de archivo. Usá el botón Descargar para
                guardarlo en tu dispositivo.
              </p>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

type AttachmentCardProps = {
  attachment: ChatAttachment;
  onOpen: (attachment: ChatAttachment) => void;
};

export function AttachmentCard({ attachment, onOpen }: AttachmentCardProps) {
  const size = formatFileSize(attachment.size_bytes);
  return (
    <button
      type="button"
      onClick={() => onOpen(attachment)}
      className="mt-2 flex w-full max-w-sm items-center gap-3 rounded-2xl border border-primary/20 bg-primary/5 px-3 py-2.5 text-left transition hover:border-primary/40 hover:bg-primary/10"
    >
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary/15">
        <FileText size={16} className="text-primary" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-foreground">{attachment.filename}</p>
        <p className="text-xs text-muted-foreground">
          {attachmentIconLabel(attachment.mime)}
          {size ? ` · ${size}` : ""}
        </p>
      </div>
    </button>
  );
}
