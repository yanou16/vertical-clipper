import { useState } from "react";
import type { Project, ProjectStatus } from "../types";

const STEPS: { status: ProjectStatus; label: string }[] = [
  { status: "downloading", label: "Getting your video" },
  { status: "preparing", label: "Preparing the editor preview" },
  { status: "analyzing", label: "Finding moments and tracking faces" },
];

interface Props {
  project: Project;
  onBack: () => void;
  onRetry: () => Promise<void>;
}

export function Processing({ project, onBack, onRetry }: Props) {
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);

  async function retry() {
    setRetrying(true);
    setRetryError(null);
    try {
      await onRetry();
    } catch (e) {
      setRetryError((e as Error).message);
    } finally {
      setRetrying(false);
    }
  }

  if (project.status === "error") {
    return (
      <main className="center-card card">
        <h2>We couldn't process this video</h2>
        <p className="error">{project.error}</p>
        {retryError && <p className="error small">{retryError}</p>}
        <div className="row">
          <button className="primary" onClick={retry} disabled={retrying}>
            {retrying ? "Starting…" : "Try again"}
          </button>
          <button onClick={onBack}>Try another video</button>
        </div>
      </main>
    );
  }

  const current = Math.max(0, STEPS.findIndex((s) => s.status === project.status));
  return (
    <main className="center-card card">
      <h2>{project.title === "Downloading..." ? "Working on your video" : project.title}</h2>
      <p className="muted">
        {project.message || "This can take a few minutes for long videos."} You can leave this page open.
      </p>
      <ol className="steps">
        {STEPS.map((step, i) => (
          <li key={step.status} className={i < current ? "done" : i === current ? "active" : ""}>
            <span className="dot" />
            <span>{step.label}</span>
            {i === current && <progress value={project.progress} max={1} />}
          </li>
        ))}
      </ol>
    </main>
  );
}
