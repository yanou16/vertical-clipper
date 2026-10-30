import type { Project } from "./types";

const SERVER_DOWN =
  "Can't reach the Vertical Clipper server. Make sure it is still running (start.sh / start.bat), then try again.";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch {
    // Browsers report a stopped server as a bare "Load failed" / "Failed to fetch".
    throw new Error(SERVER_DOWN);
  }
  if (!res.ok) {
    let message = res.statusText || "Something went wrong";
    try {
      const body = await res.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail) && body.detail[0]?.msg) message = body.detail[0].msg;
    } catch {
      /* body wasn't JSON, keep the status text */
    }
    throw new Error(message);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "content-type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  listProjects: () => request<Project[]>("/api/projects"),
  getProject: (id: string) => request<Project>(`/api/projects/${id}`),
  deleteProject: (id: string) => request<void>(`/api/projects/${id}`, { method: "DELETE" }),
  createFromUrl: (url: string) => request<Project>("/api/projects/from-url", json("POST", { url })),

  /** XHR instead of fetch because fetch can't report upload progress. */
  uploadFile(file: File, onProgress: (fraction: number) => void): Promise<Project> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/projects/upload");
      xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
      xhr.onload = () => {
        let body: any = null;
        try {
          body = JSON.parse(xhr.responseText);
        } catch {
          /* ignore */
        }
        if (xhr.status >= 200 && xhr.status < 300) resolve(body as Project);
        else reject(new Error(typeof body?.detail === "string" ? body.detail : "Upload failed"));
      };
      xhr.onerror = () => reject(new Error(SERVER_DOWN));
      const form = new FormData();
      form.append("file", file);
      xhr.send(form);
    });
  },

  patchClip: (id: string, clipId: string, patch: { start?: number; end?: number; title?: string }) =>
    request<Project>(`/api/projects/${id}/clips/${clipId}`, json("PATCH", patch)),
  addClip: (id: string, start: number, end: number) =>
    request<Project>(`/api/projects/${id}/clips`, json("POST", { start, end })),
  deleteClip: (id: string, clipId: string) =>
    request<Project>(`/api/projects/${id}/clips/${clipId}`, { method: "DELETE" }),
  resegment: (id: string, target: number) =>
    request<Project>(
      `/api/projects/${id}/resegment`,
      json("POST", { target, min_len: Math.max(3, target / 2), max_len: Math.min(180, target * 2) }),
    ),
  startExports: (id: string, clipIds: string[] | null) =>
    request<Project>(`/api/projects/${id}/exports`, json("POST", { clip_ids: clipIds })),

  mediaUrl: (id: string) => `/api/projects/${id}/media`,
  clipDownloadUrl: (id: string, clipId: string) => `/api/projects/${id}/clips/${clipId}/download`,
  zipUrl: (id: string) => `/api/projects/${id}/download`,
};
