import type { ChatAttachment, ChatMessage } from "../services/api";

const DOC_LINK_RE = /\/api\/documents\/([0-9a-f-]{36})(?:\s*\(([^)]+)\))?/g;

export function extractLegacyAttachments(text: string): ChatAttachment[] {
  const attachments: ChatAttachment[] = [];
  const re = new RegExp(DOC_LINK_RE.source, "g");
  let match: RegExpExecArray | null;
  while ((match = re.exec(text)) !== null) {
    attachments.push({
      file_id: match[1],
      filename: match[2] || "documento.docx",
      mime: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    });
  }
  return attachments;
}

export function cleanMessageText(text: string): string {
  return text
    .replace(/\n?\n?Descargá el Word acá:.*$/gm, "")
    .replace(/\n?\n?Generé el archivo:.*viso debajo\./gs, "")
    .replace(/\/api\/documents\/[0-9a-f-]{36}(?:\s*\([^)]+\))?/g, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export function resolveMessageAttachments(msg: ChatMessage): ChatAttachment[] {
  if (msg.attachments?.length) return msg.attachments;
  return extractLegacyAttachments(msg.message);
}
