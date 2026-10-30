/** 83.5 -> "1:23.5" (or "1:02:03.5" for long videos). */
export function formatTime(seconds: number): string {
  const s = Math.max(0, seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = (s % 60).toFixed(1).padStart(4, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`;
}

/** Accepts "90", "1:30", "1:30.5" or "1:02:03". Returns null when it can't be understood. */
export function parseTime(text: string): number | null {
  const parts = text.trim().split(":");
  if (parts.length === 0 || parts.length > 3) return null;
  let total = 0;
  for (const part of parts) {
    if (!/^\d+(\.\d+)?$/.test(part)) return null;
    total = total * 60 + parseFloat(part);
  }
  return total;
}

export const formatDuration = (seconds: number): string => `${seconds.toFixed(1)}s`;

export const clamp = (v: number, lo: number, hi: number): number => Math.min(hi, Math.max(lo, v));

export const snap = (v: number, step = 0.1): number => Math.round(v / step) * step;
