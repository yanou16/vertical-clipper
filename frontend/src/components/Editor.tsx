import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { sameRange } from "../lib/range";
import { clamp } from "../lib/time";
import type { FaceSample, Project, Range } from "../types";
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
const OUT_HEIGHT = 1920; // exported clips are 1080x1920

const CODEC_NAMES: Record<string, string> = { h264: "H.264", hevc: "HEVC", vp9: "VP9", av1: "AV1", vp8: "VP8" };

/** "1920×1080 · AV1 · 0.5 Mb/s": what the original video really is (the preview is a lighter copy). */
function describeSource(project: Project): string {
  const parts = [`${project.width}×${project.height}`];
  if (project.video_codec) parts.push(CODEC_NAMES[project.video_codec] ?? project.video_codec.toUpperCase());
  if (project.video_kbps > 0) parts.push(`${(project.video_kbps / 1000).toFixed(1)} Mb/s`);
  return parts.join(" · ");
}

export function Editor({ project, setProject, refresh, onBack }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [selectedId, setSelectedId] = useState<string | null>(project.clips[0]?.id ?? null);
  const [live, setLive] = useState<Range | null>(null); // range while a handle is being dragged
  const [toast, setToast] = useState<string | null>(null);
  const [splitTarget, setSplitTarget] = useState(30);
  const [faces, setFaces] = useState<FaceSample[]>([]);

  const clip = project.clips.find((c) => c.id === selectedId) ?? project.clips[0] ?? null;
  const range: Range | null = live ?? (clip ? { start: clip.start, end: clip.end } : null);
  const clipsForList = project.clips.map((c) => (live && c.id === clip?.id ? { ...c, ...live } : c));

  // A 9:16 clip only uses a slice of the width, so a short source gets enlarged. Say so plainly.
  const enlargement = OUT_HEIGHT / project.height;

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

  // Faces seen during this clip, for the "click a face to follow it" boxes.
  useEffect(() => {
    setFaces([]);
    if (!clip || !project.has_faces) return;
    let stale = false;
    api
      .getFaces(project.id, clip.start, clip.end)
      .then((samples) => !stale && setFaces(samples))
      .catch(() => {
        /* face boxes are a bonus, the editor works without them */
      });
    return () => {
      stale = true;
    };
  }, [project.id, project.has_faces, clip?.id, clip?.start, clip?.end]);

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

  // --- manual framing ---------------------------------------------------------------------------
  function saveFraming(keyframes: [number, number][]) {
    if (!clip) return;
    setProject({ ...project, clips: project.clips.map((c) => (c.id === clip.id ? { ...c, keyframes } : c)) });
    run(api.patchClip(project.id, clip.id, { keyframes }));
  }

  function addKeyframe(t: number, cx: number) {
    if (!clip) return;
    const time = Math.round(t * 100) / 100;
    const centre = Math.round(cx * 10000) / 10000;
    // A new point replaces any point placed within 0.3 s, so a re-drag corrects instead of piling up.
    const kept = clip.keyframes.filter(([kt]) => Math.abs(kt - time) > 0.3);
    saveFraming([...kept, [time, centre] as [number, number]].sort((a, b) => a[0] - b[0]));
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
        <span className="source-info muted mono" title="The original video this project was made from">
          {describeSource(project)}
        </span>
      </div>

      {enlargement > 1.15 && (
        <p className="sharpness-hint small">
          Sharpness: this source is {project.height}p, so vertical clips are enlarged ×{enlargement.toFixed(1)}.{" "}
          {project.source === "youtube"
            ? "Create the project again with a higher quality (1440p or 4K) for cleaner, more detailed clips."
            : "A higher-resolution file gives cleaner, more detailed clips."}
        </p>
      )}

      {toast && (
        <p className="error banner" role="alert">
          {toast} <button className="ghost" onClick={() => setToast(null)}>Dismiss</button>
        </p>
      )}

      <div className="editor-grid">
        <section className="stage">
          {clip && range ? (
            <>
              <PreviewPlayer
                project={project}
                clip={clip}
                range={range}
                faces={faces}
                videoRef={videoRef}
                onKeyframe={addKeyframe}
                onResetFraming={() => saveFraming([])}
              />
              <Timeline
                duration={project.duration}
                range={range}
                others={project.clips.filter((c) => c.id !== clip.id)}
                keyframes={clip.keyframes}
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
          onCancel={(ids) => run(api.cancelExports(project.id, ids))}
        />
      </div>
    </div>
  );
}
