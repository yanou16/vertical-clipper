export type ProjectStatus = "queued" | "downloading" | "preparing" | "analyzing" | "ready" | "error";
export type ExportStatus = "idle" | "queued" | "rendering" | "done" | "error";

export interface Clip {
  id: string;
  start: number;
  end: number;
  title: string;
  export_status: ExportStatus;
  export_progress: number;
  export_error: string | null;
  exported_range: [number, number] | null;
}

export interface Project {
  id: string;
  title: string;
  source: "youtube" | "upload";
  source_url: string | null;
  status: ProjectStatus;
  progress: number;
  message: string;
  error: string | null;
  duration: number;
  width: number;
  height: number;
  fps: number;
  clips: Clip[];
  /** Camera path for the 9:16 window: [time_s, centre_x (0..1)] */
  crop_path: [number, number][];
  tracking: "faces" | "center";
  created_at: number;
}

export interface Range {
  start: number;
  end: number;
}

/** A finished export that still matches the clip's current boundaries. */
export const isExportCurrent = (c: Clip): boolean =>
  c.export_status === "done" &&
  c.exported_range !== null &&
  c.exported_range[0] === c.start &&
  c.exported_range[1] === c.end;

export const isBusy = (c: Clip): boolean => c.export_status === "queued" || c.export_status === "rendering";
