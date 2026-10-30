import { useEffect, useRef, useState, type RefObject } from "react";
import { api } from "../api";
import { centerAt, cropWidthFraction } from "../lib/crop";
import { clamp, formatTime } from "../lib/time";
import type { Project, Range } from "../types";

interface Props {
  project: Project;
  range: Range;
  videoRef: RefObject<HTMLVideoElement | null>;
}

/**
 * Shows the source with the 9:16 window overlaid, next to a live canvas of exactly what the
 * exported vertical clip will look like. Playback loops inside the selected clip.
 */
export function PreviewPlayer({ project, range, videoRef }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const windowRef = useRef<HTMLDivElement>(null);
  const rangeRef = useRef(range);
  rangeRef.current = range; // read inside the animation loop without re-subscribing
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(range.start);

  const cropFrac = cropWidthFraction(project.width, project.height);

  // One animation loop: loop the clip, move the overlay, repaint the vertical canvas.
  useEffect(() => {
    let raf = 0;
    let lastLabel = 0;
    const tick = () => {
      const video = videoRef.current;
      const canvas = canvasRef.current;
      if (video && canvas && video.videoWidth) {
        const { start, end } = rangeRef.current;
        if (!video.paused && video.currentTime >= end) video.currentTime = start;

        const cx = centerAt(project.crop_path, video.currentTime);
        const left = clamp(cx - cropFrac / 2, 0, 1 - cropFrac);
        if (windowRef.current) {
          windowRef.current.style.left = `${left * 100}%`;
          windowRef.current.style.width = `${cropFrac * 100}%`;
        }
        const ctx = canvas.getContext("2d");
        ctx?.drawImage(
          video, left * video.videoWidth, 0, cropFrac * video.videoWidth, video.videoHeight,
          0, 0, canvas.width, canvas.height,
        );
        if (performance.now() - lastLabel > 100) {
          lastLabel = performance.now();
          setTime(video.currentTime);
        }
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [project.crop_path, cropFrac, videoRef]);

  function togglePlay() {
    const video = videoRef.current;
    if (!video) return;
    if (video.paused) {
      if (video.currentTime < range.start || video.currentTime >= range.end - 0.1) video.currentTime = range.start;
      video.play();
    } else {
      video.pause();
    }
  }

  const length = range.end - range.start;
  const position = clamp(time - range.start, 0, length);

  return (
    <div className="player">
      <div className="player-wide">
        <div className="video-frame" style={{ aspectRatio: `${project.width} / ${project.height}` }}>
          <video
            ref={videoRef}
            src={api.mediaUrl(project.id)}
            preload="auto"
            playsInline
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
            onClick={togglePlay}
          />
          <div className="crop-window" ref={windowRef} />
        </div>
        <p className="muted small">
          {project.tracking === "faces"
            ? "The bright frame follows the speaker. Preview is low-res; exports are full quality."
            : "No faces found, so the crop stays centred. Preview is low-res; exports are full quality."}
        </p>
      </div>

      <div className="player-vertical">
        <canvas ref={canvasRef} width={360} height={640} />
        <div className="player-controls">
          <button onClick={togglePlay}>
            {playing ? "Pause" : "Play clip"}
          </button>
          <span className="mono">
            {formatTime(position)} / {formatTime(length)}
          </span>
        </div>
      </div>
    </div>
  );
}
