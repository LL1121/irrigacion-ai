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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/70 p-4 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-2xl border border-border bg-panel shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <div>
            <h3 className="text-sm font-semibold text-text">Indexar documentos</h3>
            <p className="text-xs text-muted">PDF, Word o imágenes escaneadas</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1.5 text-muted transition hover:bg-panel-2 hover:text-text"
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
            className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed px-6 py-10 transition ${
              dragging
                ? "border-accent bg-accent/10"
                : "border-border bg-panel-2 hover:border-accent/40"
            }`}
          >
            <FileUp className="mb-3 text-accent" size={28} />
            <p className="text-sm font-medium text-text">
              Arrastrá archivos aquí o hacé clic
            </p>
            <p className="mt-1 text-xs text-muted">.pdf · .docx · .png · .jpg</p>
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
            <div className="flex items-center gap-2 text-sm text-muted">
              <LoaderCircle className="animate-spin" size={16} />
              Procesando e indexando…
            </div>
          )}

          {error && (
            <p className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
              {error}
            </p>
          )}

          {results && (
            <ul className="max-h-40 space-y-2 overflow-y-auto text-xs">
              {results.map((item) => (
                <li
                  key={`${item.filename}-${item.chunks_created}`}
                  className="rounded-lg border border-border bg-panel-2 px-3 py-2"
                >
                  <div className="font-medium text-text">{item.filename}</div>
                  <div className="text-muted">
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
