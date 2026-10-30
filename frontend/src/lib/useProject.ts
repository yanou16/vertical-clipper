import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { isBusy, type Project } from "../types";

const POLL_MS = 1000;

/** Loads a project and keeps it fresh while the server is still working on it. */
export function useProject(id: string) {
  const [project, setProject] = useState<Project | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setProject(await api.getProject(id));
      setLoadError(null);
    } catch (e) {
      setLoadError((e as Error).message);
    }
  }, [id]);

  useEffect(() => {
    setProject(null);
    refresh();
  }, [refresh]);

  const working =
    project !== null &&
    (project.status !== "ready" && project.status !== "error" ? true : project.clips.some(isBusy));

  useEffect(() => {
    if (!working) return;
    const timer = setInterval(refresh, POLL_MS);
    return () => clearInterval(timer);
  }, [working, refresh]);

  return { project, setProject, loadError, refresh };
}
