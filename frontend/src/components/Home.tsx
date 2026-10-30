import { useEffect, useRef, useState, type DragEvent, type FormEvent } from "react";
import { api } from "../api";
import type { Project } from "../types";

interface Props {
  onOpen: (id: string) => void;
}

export function Home({ onOpen }: Props) {
  const [url, setUrl] = useState("");
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
      onOpen((await api.createFromUrl(url.trim())).id);
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
        <button className="primary" disabled={busy || !url.trim()}>
          Create clips
        </button>
      </form>

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
