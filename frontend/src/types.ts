export type ProjectStatus = "queued" | "downloading" | "preparing" | "analyzing" | "ready" | "error";
export type ExportStatus = "idle" | "queued" | "rendering" | "done" | "error";

export interface Clip {
  id: string;
  start: number;
  end: number;
  title: string;
  /** Manual framing points [time_s, centre_x 0..1]. Empty = automatic camera. */
  keyframes: [number, number][];
  /** Bumped by the server whenever the range or framing changes. */
  revision: number;
  export_status: ExportStatus;
  export_progress: number;
  export_error: string | null;
  exported_revision: number | null;
}

export interface Project {
  id: string;
  title: string;
  source: "youtube" | "upload";
  source_url: string | null;
  quality: number;
  status: ProjectStatus;
  progress: number;
  message: string;
  error: string | null;
  duration: number;
  width: number;
  height: number;
  fps: number;
  video_codec: string;
  video_kbps: number;
  clips: Clip[];
  /** Automatic camera path for the 9:16 window: [time_s, centre_x (0..1)] */
  crop_path: [number, number][];
  tracking: "faces" | "center";
  has_faces: boolean;
  created_at: number;
}

export interface Range {
  start: number;
  end: number;
}

/** A face seen in the video, as fractions (0..1) of the frame. */
export interface FaceBox {
  cx: number;
  cy: number;
  w: number;
  h: number;
}

export interface FaceSample {
  t: number;
  faces: FaceBox[];
}

/** A finished export that reflects the clip as it is now (same range and same framing). */
export const isExportCurrent = (c: Clip): boolean =>
  c.export_status === "done" && c.exported_revision === c.revision;

export const isBusy = (c: Clip): boolean => c.export_status === "queued" || c.export_status === "rendering";
