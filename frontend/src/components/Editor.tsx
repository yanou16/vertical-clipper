import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { sameRange } from "../lib/range";
import { clamp } from "../lib/time";
import type { Project, Range } from "../types";
import { ClipList } from "./ClipList";
import { PreviewPlayer } from "./PreviewPlayer";
import { Timeline, type Focus } from "./Timeline";
import { TrimControls } from "./TrimControls";

interface Props {
  project: Project;
  setProject: (p: Project) => void;
  refresh: () => void;
  onBack: () => void;
}

const SPLIT_LENGTHS = [15, 30, 45, 60];

export function Editor({ project, setProject, refresh, onBack }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [selectedId, setSelectedId] = useState<string | null>(project.clips[0]?.id ?? null);
  const [live, setLive] = useState<Range | null>(null); // range while a handle is being dragged
  const [toast, setToast] = useState<string | null>(null);
  const [splitTarget, setSplitTarget] = useState(30);

  const clip = project.clips.find((c) => c.id === selectedId) ?? project.clips[0] ?? null;
  const range: Range | null = live ?? (clip ? { start: clip.start, end: clip.end } : null);
  const clipsForList = project.clips.map((c) => (live && c.id === clip?.id ? { ...c, ...live } : c));

  const seek = (t: number) => {
    if (videoRef.current) videoRef.current.currentTime = clamp(t, 0, project.duration);
  };

  // Jump to the start of a clip whenever the selection changes.
  useEffect(() => {
    if (clip) {
      setLive(null);
      seek(clip.start);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clip?.id]);

  async function run(promise: Promise<Project>): Promise<Project | null> {
    try {
      const updated = await promise;
      setProject(updated);
      setToast(null);
      return updated;
    } catch (e) {
      setToast((e as Error).message);
      refresh(); // resync with the server after a failed optimistic update
      return null;
    }
  }

  function commit(r: Range, focus: Focus) {
    setLive(null);
    if (!clip || sameRange(r, clip)) return;
    // Optimistic: show the new boundaries immediately, the server answer replaces them.
    setProject({ ...project, clips: project.clips.map((c) => (c.id === clip.id ? { ...c, ...r } : c)) });
    seek(focus === "end" ? r.end - 0.5 : r.start);
    run(api.patchClip(project.id, clip.id, r));
  }

  async function addClip() {
    const start = clamp(videoRef.current?.currentTime ?? 0, 0, Math.max(0, project.duration - 1));
    const end = Math.min(project.duration, start + 30);
    const updated = await run(api.addClip(project.id, start, end));
    const created = updated?.clips.find((c) => Math.abs(c.start - start) < 0.02 && Math.abs(c.end - end) < 0.02);
    if (created) setSelectedId(created.id);
  }

  async function removeClip(id: string) {
    if (!confirm("Delete this clip?")) return;
    const index = project.clips.findIndex((c) => c.id === id);
    const updated = await run(api.deleteClip(project.id, id));
    if (updated && id === clip?.id) setSelectedId(updated.clips[Math.min(index, updated.clips.length - 1)]?.id ?? null);
  }

  async function resegment() {
    if (!confirm("Replace all clips with a fresh automatic split? Your manual changes will be lost.")) return;
    const updated = await run(api.resegment(project.id, splitTarget));
    setSelectedId(updated?.clips[0]?.id ?? null);
  }

  return (
    <div className="editor">
      <div className="editor-head">
        <button className="ghost" onClick={onBack}>
          ← New video
        </button>
        <h1 title={project.title}>{project.title}</h1>
      </div>

      {toast && (
        <p className="error banner" role="alert">
          {toast} <button className="ghost" onClick={() => setToast(null)}>Dismiss</button>
        </p>
      )}

      <div className="editor-grid">
        <section className="stage">
          {clip && range ? (
            <>
              <PreviewPlayer project={project} range={range} videoRef={videoRef} />
              <Timeline
                duration={project.duration}
                range={range}
                others={project.clips.filter((c) => c.id !== clip.id)}
                videoRef={videoRef}
                onLive={setLive}
                onCommit={commit}
              />
              <TrimControls duration={project.duration} range={range} onCommit={commit} />
            </>
          ) : (
            <p className="card muted">No clips yet. Add one below, or re-run the automatic split.</p>
          )}

          <div className="toolbar">
            <button onClick={addClip}>＋ Add a clip at the playhead</button>
            <span className="spacer" />
            <label className="muted small" htmlFor="split">Auto-split into ~</label>
            <select id="split" value={splitTarget} onChange={(e) => setSplitTarget(Number(e.target.value))}>
              {SPLIT_LENGTHS.map((s) => (
                <option key={s} value={s}>
                  {s}s clips
                </option>
              ))}
            </select>
            <button onClick={resegment}>Re-split</button>
          </div>
        </section>

        <ClipList
          project={project}
          clips={clipsForList}
          selectedId={clip?.id ?? null}
          onSelect={setSelectedId}
          onRename={(id, title) => run(api.patchClip(project.id, id, { title }))}
          onDelete={removeClip}
          onExport={(ids) => run(api.startExports(project.id, ids))}
        />
      </div>
    </div>
  );
}
