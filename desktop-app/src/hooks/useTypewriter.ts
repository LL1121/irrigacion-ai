import { useEffect, useState } from "react";

/**
 * Revela texto con efecto máquina de escribir: empieza lento, acelera y
 * completa de golpe pasado un umbral para no volver tedioso el uso diario.
 */
export function useTypewriter(text: string, enabled: boolean): string {
  const [visible, setVisible] = useState(enabled ? "" : text);

  useEffect(() => {
    if (!enabled) {
      setVisible(text);
      return;
    }

    setVisible("");
    let index = 0;
    let delayMs = 32;
    const flushAt = Math.min(140, Math.max(40, Math.floor(text.length * 0.35)));
    let timer: ReturnType<typeof setTimeout> | undefined;
    let cancelled = false;

    const tick = () => {
      if (cancelled) return;
      if (index >= text.length) return;

      if (index >= flushAt) {
        setVisible(text);
        return;
      }

      index += 1;
      setVisible(text.slice(0, index));
      delayMs = Math.max(6, delayMs * 0.9);
      timer = setTimeout(tick, delayMs);
    };

    timer = setTimeout(tick, delayMs);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [text, enabled]);

  return visible;
}
