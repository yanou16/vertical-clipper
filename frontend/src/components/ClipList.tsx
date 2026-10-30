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
  onCancel: (ids: string[] | null) => void;
}

export function ClipList({ project, clips, selectedId, onSelect, onRename, onDelete, onExport, onCancel }: Props) {
  const [checked, setChecked] = useState<Set<string>>(new Set());

  // Ticked clips that still exist (a deleted clip silently drops out of the selection).
  const picked = clips.filter((c) => checked.has(c.id));
  const needsExport = (c: Clip) => !isExportCurrent(c) && !isBusy(c);
  const pendingAll = clips.filter(needsExport);
  const pendingPicked = picked.filter(needsExport);
  const ready = clips.filter(isExportCurrent).length;
  const exporting = clips.some(isBusy);
  const allPicked = clips.length > 0 && picked.length === clips.length;

  const toggle = (id: string) =>
    setChecked((prev) => {
      const next = new Set(prev);
      if (!next.delete(id)) next.add(id);
      return next;
    });

  const exportCount = picked.length > 0 ? pendingPicked.length : pendingAll.length;

  return (
    <aside className="clip-list">
      <div className="clip-list-head">
        <h2>
          Clips <span className="muted">({clips.length})</span>
        </h2>
        <div className="row tight">
          <button
            className="primary"
            disabled={exportCount === 0}
            onClick={() => onExport(picked.length > 0 ? pendingPicked.map((c) => c.id) : null)}
          >
            {picked.length > 0 ? `Export selected (${exportCount})` : `Export all (${exportCount})`}
          </button>
          {ready > 0 && (
            <a className="button" href={api.zipUrl(project.id)} download>
              Download ZIP ({ready})
            </a>
          )}
        </div>
        <div className="row list-tools">
          <label className="select-all">
            <input
              type="checkbox"
              checked={allPicked}
              onChange={() => setChecked(allPicked ? new Set() : new Set(clips.map((c) => c.id)))}
            />
            {picked.length > 0 ? `${picked.length} selected` : "Select all"}
          </label>
          <span className="spacer" />
          {exporting && (
            <button className="ghost danger" onClick={() => onCancel(picked.length > 0 ? picked.map((c) => c.id) : null)}>
              {picked.length > 0 ? "Stop selected" : "Stop all"}
            </button>
          )}
        </div>
      </div>

      <ul>
        {clips.map((clip, i) => (
          <li key={clip.id} className={clip.id === selectedId ? "selected" : ""} onClick={() => onSelect(clip.id)}>
            <div className="clip-title">
              <input
                type="checkbox"
                aria-label={`Select clip ${i + 1}`}
                checked={checked.has(clip.id)}
                onChange={() => toggle(clip.id)}
                onClick={(e) => e.stopPropagation()}
              />
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
              {clip.keyframes.length > 0 && <span className="muted"> · framed by hand</span>}
            </div>
            <ExportStatus
              project={project}
              clip={clip}
              onExport={() => onExport([clip.id])}
              onCancel={() => onCancel([clip.id])}
            />
          </li>
        ))}
      </ul>
    </aside>
  );
}

function ExportStatus({ project, clip, onExport, onCancel }: {
  project: Project;
  clip: Clip;
  onExport: () => void;
  onCancel: () => void;
}) {
  const stop = (e: React.MouseEvent) => e.stopPropagation();
  if (isBusy(clip)) {
    return (
      <div className="export-row" onClick={stop}>
        <progress value={clip.export_status === "queued" ? 0 : clip.export_progress} max={1} />
        <span className="muted small">{clip.export_status === "queued" ? "Waiting…" : "Rendering…"}</span>
        <button className="ghost" onClick={onCancel}>
          Cancel
        </button>
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
