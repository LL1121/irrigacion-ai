import { useRef, useState, type DragEvent } from "react";
import { FileUp, LoaderCircle, X } from "lucide-react";
import { uploadFiles, type UploadResult } from "../services/api";

type FileUploadModalProps = {
  open: boolean;
  onClose: () => void;
};

const ACCEPTED =
  ".pdf,.docx,.png,.jpg,.jpeg,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,image/png,image/jpeg";

export function FileUploadModal({ open, onClose }: FileUploadModalProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [results, setResults] = useState<UploadResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  async function handleFiles(fileList: FileList | File[]) {
    const files = Array.from(fileList);
    if (!files.length) return;
    setUploading(true);
    setError(null);
    setResults(null);
    try {
      const response = await uploadFiles(files);
      setResults(response.results);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al subir archivos");
    } finally {
      setUploading(false);
    }
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    if (event.dataTransfer.files?.length) {
      void handleFiles(event.dataTransfer.files);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/20 p-4 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-3xl border border-border bg-background shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <div>
            <h3 className="text-sm text-foreground" style={{ fontWeight: 600 }}>
              Indexar documentos
            </h3>
            <p className="text-xs text-muted-foreground">PDF, Word o imágenes escaneadas</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-xl text-muted-foreground transition-all hover:bg-muted hover:text-foreground"
          >
            <X size={16} />
          </button>
        </div>

        <div className="space-y-4 p-5">
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => inputRef.current?.click()}
            className={`flex cursor-pointer flex-col items-center justify-center rounded-2xl border border-dashed px-6 py-10 transition ${
              dragging
                ? "border-primary bg-primary/10"
                : "border-border bg-muted/40 hover:border-primary/40"
            }`}
          >
            <FileUp className="mb-3 text-primary" size={28} />
            <p className="text-sm text-foreground" style={{ fontWeight: 500 }}>
              Arrastrá archivos aquí o hacé clic
            </p>
            <p className="mt-1 text-xs text-muted-foreground">.pdf · .docx · .png · .jpg</p>
            <input
              ref={inputRef}
              type="file"
              multiple
              accept={ACCEPTED}
              className="hidden"
              onChange={(e) => {
                if (e.target.files) void handleFiles(e.target.files);
              }}
            />
          </div>

          {uploading && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <LoaderCircle className="animate-spin" size={16} />
              Procesando e indexando…
            </div>
          )}

          {error && (
            <p className="rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
              {error}
            </p>
          )}

          {results && (
            <ul className="max-h-40 space-y-2 overflow-y-auto text-xs">
              {results.map((item) => (
                <li
                  key={`${item.filename}-${item.chunks_created}`}
                  className="rounded-xl border border-border bg-card px-3 py-2"
                >
                  <div className="text-foreground" style={{ fontWeight: 500 }}>
                    {item.filename}
                  </div>
                  <div className="text-muted-foreground">
                    {item.error
                      ? `Error: ${item.error}`
                      : `${item.chunks_created} chunks creados`}
                    {item.warning ? ` · ${item.warning}` : ""}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
