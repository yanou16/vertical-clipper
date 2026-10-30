import { useEffect, useRef, useState, type DragEvent, type FormEvent } from "react";
import { api } from "../api";
import type { Project } from "../types";

interface Props {
  onOpen: (id: string) => void;
}

// Maximum height we ask YouTube for. A 9:16 clip only uses a slice of the width, so a sharper source
// gives a visibly sharper clip. Keep in sync with QUALITY_CHOICES in backend/app/config.py.
const QUALITIES = [
  { value: 2160, label: "4K (sharpest)" },
  { value: 1440, label: "1440p (recommended)" },
  { value: 1080, label: "1080p" },
  { value: 720, label: "720p (fastest)" },
];
const QUALITY_KEY = "clipper.quality";

function savedQuality(): number {
  try {
    const value = Number(localStorage.getItem(QUALITY_KEY));
    if (QUALITIES.some((q) => q.value === value)) return value;
  } catch {
    /* storage can be blocked, fall back to the default */
  }
  return 1440;
}

export function Home({ onOpen }: Props) {
  const [url, setUrl] = useState("");
  const [quality, setQuality] = useState(savedQuality);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [uploadPct, setUploadPct] = useState<number | null>(null);
  const [dragging, setDragging] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const fileInput = useRef<HTMLInputElement>(null);

  const loadProjects = () => api.listProjects().then(setProjects).catch(() => setProjects([]));
  useEffect(() => {
    loadProjects();
  }, []);

  async function submitUrl(e: FormEvent) {
    e.preventDefault();
    if (!url.trim()) return;
    setBusy(true);
    setError(null);
    try {
      try {
        localStorage.setItem(QUALITY_KEY, String(quality));
      } catch {
        /* not essential */
      }
      onOpen((await api.createFromUrl(url.trim(), quality)).id);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  async function upload(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setError(null);
    setUploadPct(0);
    try {
      onOpen((await api.uploadFile(file, setUploadPct)).id);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
      setUploadPct(null);
    }
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    if (!busy) upload(e.dataTransfer.files[0]);
  }

  async function remove(id: string) {
    if (!confirm("Delete this project and its exported clips?")) return;
    await api.deleteProject(id);
    loadProjects();
  }

  return (
    <main className="home">
      <h1>Turn long videos into vertical clips</h1>
      <p className="lead">
        Paste a YouTube link or drop a video file. We find the best moments, keep the speaker in frame, and give you
        ready-to-post 9:16 clips.
      </p>

      <form className="url-pill" onSubmit={submitUrl}>
        <span className="prompt" aria-hidden>
          $
        </span>
        <input
          id="url"
          type="url"
          aria-label="YouTube link"
          placeholder="Paste a YouTube link"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          disabled={busy}
        />
        <select
          aria-label="Download quality"
          value={quality}
          onChange={(e) => setQuality(Number(e.target.value))}
          disabled={busy}
        >
          {QUALITIES.map((q) => (
            <option key={q.value} value={q.value}>
              {q.label}
            </option>
          ))}
        </select>
        <button className="primary" disabled={busy || !url.trim()}>
          Create clips
        </button>
      </form>
      <p className="quality-hint muted small">
        Vertical clips use a slice of the picture, so a sharper download gives sharper clips. Higher quality means a
        bigger download and slower exports.
      </p>

      <div className="or">or</div>

      <div
        className={`dropzone ${dragging ? "dragging" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => !busy && fileInput.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && !busy && fileInput.current?.click()}
      >
        <input
          ref={fileInput}
          type="file"
          accept="video/*,.mkv"
          hidden
          onChange={(e) => upload(e.target.files?.[0])}
        />
        {uploadPct === null ? (
          <>
            <strong>Drop a video here</strong>
            <span>or click to choose a file (MP4, MOV, MKV, WebM)</span>
          </>
        ) : (
          <>
            <strong>Uploading… {Math.round(uploadPct * 100)}%</strong>
            <progress value={uploadPct} max={1} />
          </>
        )}
      </div>

      {error && <p className="error" role="alert">{error}</p>}

      {projects.length > 0 && (
        <section className="recent">
          <h2>Your projects</h2>
          <ul>
            {projects.map((p) => (
              <li key={p.id}>
                <button className="link" onClick={() => onOpen(p.id)}>
                  {p.title}
                </button>
                <span className="muted">
                  {p.status === "ready"
                    ? `${p.clips.length} ${p.clips.length === 1 ? "clip" : "clips"}`
                    : p.status === "error"
                      ? "failed"
                      : "processing…"}
                </span>
                <button className="ghost danger" onClick={() => remove(p.id)} aria-label={`Delete ${p.title}`}>
                  Delete
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
