import { useEffect, useState } from "react";
import { api } from "./api";
import { Editor } from "./components/Editor";
import { Home } from "./components/Home";
import { Processing } from "./components/Processing";
import { useProject } from "./lib/useProject";

/** Tiny hash router: "#/p/<id>" opens a project, anything else is the home page. */
function useProjectIdFromHash(): string | null {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const onChange = () => setHash(window.location.hash);
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return hash.match(/^#\/p\/([a-f0-9]{12})$/)?.[1] ?? null;
}

const open = (id: string) => (window.location.hash = `#/p/${id}`);
const home = () => (window.location.hash = "");

function ProjectPage({ id }: { id: string }) {
  const { project, setProject, loadError, refresh } = useProject(id);

  if (loadError) {
    return (
      <main className="center-card card">
        <h2>Project not found</h2>
        <p className="error">{loadError}</p>
        <button className="primary" onClick={home}>
          Back to start
        </button>
      </main>
    );
  }
  if (!project) return <main className="center-card muted">Loading…</main>;
  if (project.status !== "ready") {
    return <Processing project={project} onBack={home} onRetry={async () => setProject(await api.retry(id))} />;
  }
  return <Editor key={project.id} project={project} setProject={setProject} refresh={refresh} onBack={home} />;
}

export default function App() {
  const id = useProjectIdFromHash();
  return (
    <>
      <header className="app-header">
        <a href="#" className="brand">
          <span className="slash">/</span>clipper
        </a>
      </header>
      {id ? <ProjectPage id={id} /> : <Home onOpen={open} />}
    </>
  );
}
