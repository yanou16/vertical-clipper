import { useEffect, useRef, type KeyboardEvent, type PointerEvent, type RefObject } from "react";
import { clamp, formatTime } from "../lib/time";
import { moveEnd, moveStart, slide } from "../lib/range";
import type { Clip, Range } from "../types";

export type Focus = "start" | "end";
type DragKind = "start" | "end" | "move";

interface Props {
  duration: number;
  range: Range;
  others: Clip[]; // the other clips, drawn faintly for context
  videoRef: RefObject<HTMLVideoElement | null>;
  onLive: (r: Range) => void; // while dragging
  onCommit: (r: Range, focus: Focus) => void; // when released
}

/** Zoomed timeline around the selected clip, with draggable start/end handles. */
export function Timeline({ duration, range, others, videoRef, onLive, onCommit }: Props) {
  const trackRef = useRef<HTMLDivElement>(null);
  const playheadRef = useRef<HTMLDivElement>(null);
  const drag = useRef<{ kind: DragKind; x: number; origin: Range; view: View; latest: Range } | null>(null);

  // While dragging we freeze the zoom window, otherwise the track would move under the pointer.
  const view = drag.current?.view ?? viewFor(range, duration);
  const span = view.hi - view.lo;
  const pct = (t: number) => ((t - view.lo) / span) * 100;

  useEffect(() => {
    let raf = 0;
    const tick = () => {
      const el = playheadRef.current;
      const video = videoRef.current;
      if (el && video) {
        const p = ((video.currentTime - view.lo) / span) * 100;
        el.style.display = p < 0 || p > 100 ? "none" : "block";
        el.style.left = `${p}%`;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [view.lo, span, videoRef]);

  function seek(t: number) {
    if (videoRef.current) videoRef.current.currentTime = clamp(t, 0, duration);
  }

  function begin(kind: DragKind, e: PointerEvent) {
    e.stopPropagation();
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { kind, x: e.clientX, origin: range, view: viewFor(range, duration), latest: range };
  }

  function move(e: PointerEvent) {
    const d = drag.current;
    if (!d || !trackRef.current) return;
    const dt = ((e.clientX - d.x) / trackRef.current.clientWidth) * (d.view.hi - d.view.lo);
    let next: Range;
    if (d.kind === "start") next = moveStart(d.origin, d.origin.start + dt);
    else if (d.kind === "end") next = moveEnd(d.origin, d.origin.end + dt, duration);
    else next = slide(d.origin, d.origin.start + dt, duration);
    d.latest = next;
    onLive(next);
    seek(d.kind === "end" ? next.end - 0.3 : next.start);
  }

  function finish() {
    const d = drag.current;
    drag.current = null;
    if (d) onCommit(d.latest, d.kind === "end" ? "end" : "start");
  }

  function onKey(kind: "start" | "end", e: KeyboardEvent) {
    const step = e.key === "ArrowLeft" ? -1 : e.key === "ArrowRight" ? 1 : 0;
    if (!step) return;
    e.preventDefault();
    const delta = step * (e.shiftKey ? 1 : 0.1);
    onCommit(kind === "start" ? moveStart(range, range.start + delta) : moveEnd(range, range.end + delta, duration), kind);
  }

  function onTrackClick(e: PointerEvent) {
    const rect = e.currentTarget.getBoundingClientRect();
    seek(view.lo + ((e.clientX - rect.left) / rect.width) * span);
  }

  return (
    <div className="timeline">
      <div className="track" ref={trackRef} onPointerDown={onTrackClick}>
        {others
          .filter((c) => c.end > view.lo && c.start < view.hi)
          .map((c) => {
            const left = Math.max(0, pct(c.start));
            const right = Math.min(100, pct(c.end));
            return <div key={c.id} className="other-clip" style={{ left: `${left}%`, width: `${right - left}%` }} />;
          })}
        <div
          className="selected-clip"
          style={{ left: `${pct(range.start)}%`, width: `${pct(range.end) - pct(range.start)}%` }}
          onPointerDown={(e) => begin("move", e)}
          onPointerMove={move}
          onPointerUp={finish}
          title="Drag to slide the whole clip"
        />
        <Handle side="start" at={pct(range.start)} value={range.start} begin={begin} move={move} finish={finish} onKey={onKey} />
        <Handle side="end" at={pct(range.end)} value={range.end} begin={begin} move={move} finish={finish} onKey={onKey} />
        <div className="playhead" ref={playheadRef} />
      </div>
      <div className="timeline-labels mono">
        <span>{formatTime(view.lo)}</span>
        <span>{formatTime(view.hi)}</span>
      </div>
    </div>
  );
}

interface View {
  lo: number;
  hi: number;
}

function viewFor(range: Range, duration: number): View {
  const pad = Math.max(10, (range.end - range.start) * 0.5);
  return { lo: Math.max(0, range.start - pad), hi: Math.min(duration, range.end + pad) };
}

interface HandleProps {
  side: "start" | "end";
  at: number;
  value: number;
  begin: (k: DragKind, e: PointerEvent) => void;
  move: (e: PointerEvent) => void;
  finish: () => void;
  onKey: (k: "start" | "end", e: KeyboardEvent) => void;
}

function Handle({ side, at, value, begin, move, finish, onKey }: HandleProps) {
  return (
    <div
      className={`handle ${side}`}
      style={{ left: `${at}%` }}
      role="slider"
      tabIndex={0}
      aria-label={side === "start" ? "Clip start" : "Clip end"}
      aria-valuenow={Math.round(value * 10) / 10}
      aria-valuetext={formatTime(value)}
      onPointerDown={(e) => begin(side, e)}
      onPointerMove={move}
      onPointerUp={finish}
      onKeyDown={(e) => onKey(side, e)}
    />
  );
}
