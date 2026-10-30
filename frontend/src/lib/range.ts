import type { Range } from "../types";
import { clamp } from "./time";

// Keep in sync with CLIP_MIN_LEN / CLIP_MAX_LEN in backend/app/config.py.
export const MIN_LEN = 1;
export const MAX_LEN = 180;

const tenth = (v: number) => Math.round(v * 10) / 10;

export function moveStart(r: Range, start: number): Range {
  return { start: clamp(tenth(start), Math.max(0, r.end - MAX_LEN), r.end - MIN_LEN), end: r.end };
}

export function moveEnd(r: Range, end: number, duration: number): Range {
  return { start: r.start, end: clamp(tenth(end), r.start + MIN_LEN, Math.min(duration, r.start + MAX_LEN)) };
}

/** Slide the whole clip without changing its length. */
export function slide(r: Range, start: number, duration: number): Range {
  const length = r.end - r.start;
  const s = clamp(tenth(start), 0, Math.max(0, duration - length));
  return { start: s, end: s + length };
}

export const sameRange = (a: Range, b: Range) => a.start === b.start && a.end === b.end;
