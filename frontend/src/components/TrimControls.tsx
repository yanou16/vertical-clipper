import { useEffect, useState } from "react";
import { formatDuration, formatTime, parseTime } from "../lib/time";
import { moveEnd, moveStart } from "../lib/range";
import type { Range } from "../types";
import type { Focus } from "./Timeline";

interface Props {
  duration: number;
  range: Range;
  onCommit: (r: Range, focus: Focus) => void;
}

/** Precise, button-based editing for people who don't want to drag handles. */
export function TrimControls({ duration, range, onCommit }: Props) {
  const length = range.end - range.start;
  return (
    <div className="trim-controls">
      <TimeField label="Start" value={range.start} onChange={(t) => onCommit(moveStart(range, t), "start")}>
        <button onClick={() => onCommit(moveStart(range, range.start - 1), "start")}>−1s</button>
        <button onClick={() => onCommit(moveStart(range, range.start + 1), "start")}>+1s</button>
      </TimeField>

      <TimeField label="End" value={range.end} onChange={(t) => onCommit(moveEnd(range, t, duration), "end")}>
        <button onClick={() => onCommit(moveEnd(range, range.end - 1, duration), "end")}>−1s</button>
        <button onClick={() => onCommit(moveEnd(range, range.end + 1, duration), "end")}>+1s</button>
      </TimeField>

      <div className="field">
        <span className="field-label">Length · {formatDuration(length)}</span>
        <div className="row tight">
          <button onClick={() => onCommit(moveEnd(range, range.end - 5, duration), "end")}>Shorter 5s</button>
          <button onClick={() => onCommit(moveEnd(range, range.end - 1, duration), "end")}>−1s</button>
          <button onClick={() => onCommit(moveEnd(range, range.end + 1, duration), "end")}>+1s</button>
          <button onClick={() => onCommit(moveEnd(range, range.end + 5, duration), "end")}>Longer 5s</button>
        </div>
      </div>
    </div>
  );
}

function TimeField({ label, value, onChange, children }: {
  label: string;
  value: number;
  onChange: (t: number) => void;
  children: React.ReactNode;
}) {
  const [text, setText] = useState(formatTime(value));
  const [invalid, setInvalid] = useState(false);
  useEffect(() => {
    setText(formatTime(value));
    setInvalid(false);
  }, [value]);

  function commit() {
    const parsed = parseTime(text);
    if (parsed === null) {
      setInvalid(true);
      return;
    }
    setInvalid(false);
    onChange(parsed);
    setText(formatTime(parsed)); // snaps back to the accepted value if it was clamped
  }

  return (
    <div className="field">
      <label className="field-label">{label}</label>
      <div className="row tight">
        <input
          className={`mono time-input ${invalid ? "invalid" : ""}`}
          value={text}
          aria-invalid={invalid}
          onChange={(e) => setText(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => e.key === "Enter" && (e.currentTarget.blur(), undefined)}
        />
        {children}
      </div>
    </div>
  );
}
