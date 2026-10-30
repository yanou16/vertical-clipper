import { useState } from "react";
import { api } from "../api";
import { formatDuration, formatTime } from "../lib/time";
import { isBusy, isExportCurrent, type Clip, type Project } from "../types";

interface Props {
  project: Project;
  clips: Clip[]; // with the live (being dragged) range applied
  selectedId: string | null;
  onSelect: (id: string) => void;
  onRename: (id: string, title: string) => void;
  onDelete: (id: string) => void;
  onExport: (ids: string[] | null) => void;
}

export function ClipList({ project, clips, selectedId, onSelect, onRename, onDelete, onExport }: Props) {
  const ready = clips.filter(isExportCurrent).length;
  const pending = clips.filter((c) => !isExportCurrent(c) && !isBusy(c)).length;
  const exporting = clips.some(isBusy);

  return (
    <aside className="clip-list">
      <div className="clip-list-head">
        <h2>
          Clips <span className="muted">({clips.length})</span>
        </h2>
        <div className="row tight">
          <button className="primary" disabled={pending === 0} onClick={() => onExport(null)}>
            {exporting ? "Exporting…" : `Export all (${pending})`}
          </button>
          {ready > 0 && (
            <a className="button" href={api.zipUrl(project.id)} download>
              Download ZIP ({ready})
            </a>
          )}
        </div>
      </div>

      <ul>
        {clips.map((clip, i) => (
          <li key={clip.id} className={clip.id === selectedId ? "selected" : ""} onClick={() => onSelect(clip.id)}>
            <div className="clip-title">
              <span className="index">{i + 1}</span>
              <TitleInput value={clip.title} onCommit={(t) => onRename(clip.id, t)} />
              <button
                className="ghost danger"
                aria-label={`Delete clip ${i + 1}`}
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(clip.id);
                }}
              >
                ✕
              </button>
            </div>
            <div className="clip-meta mono">
              {formatTime(clip.start)} → {formatTime(clip.end)} · {formatDuration(clip.end - clip.start)}
            </div>
            <ExportStatus project={project} clip={clip} onExport={() => onExport([clip.id])} />
          </li>
        ))}
      </ul>
    </aside>
  );
}

function ExportStatus({ project, clip, onExport }: { project: Project; clip: Clip; onExport: () => void }) {
  const stop = (e: React.MouseEvent) => e.stopPropagation();
  if (isBusy(clip)) {
    return (
      <div className="export-row" onClick={stop}>
        <progress value={clip.export_status === "queued" ? 0 : clip.export_progress} max={1} />
        <span className="muted small">{clip.export_status === "queued" ? "Waiting…" : "Rendering…"}</span>
      </div>
    );
  }
  if (isExportCurrent(clip)) {
    return (
      <div className="export-row" onClick={stop}>
        <a className="button" href={api.clipDownloadUrl(project.id, clip.id)} download>
          Download
        </a>
        <span className="muted small">Exported ✓</span>
      </div>
    );
  }
  return (
    <div className="export-row" onClick={stop}>
      <button onClick={onExport}>{clip.export_status === "error" ? "Retry export" : "Export"}</button>
      {clip.export_error && <span className="error small">{clip.export_error}</span>}
    </div>
  );
}

function TitleInput({ value, onCommit }: { value: string; onCommit: (t: string) => void }) {
  const [text, setText] = useState(value);
  const [editing, setEditing] = useState(false);
  return (
    <input
      className="title-input"
      value={editing ? text : value}
      aria-label="Clip name"
      onFocus={() => {
        setText(value);
        setEditing(true);
      }}
      onChange={(e) => setText(e.target.value)}
      onBlur={() => {
        setEditing(false);
        if (text.trim() && text !== value) onCommit(text);
      }}
      onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
      onClick={(e) => e.stopPropagation()}
    />
  );
}
