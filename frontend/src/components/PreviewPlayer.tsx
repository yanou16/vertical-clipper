import { useEffect, useMemo, useRef, useState, type PointerEvent, type RefObject } from "react";
import { api } from "../api";
import { centerAt, cropWidthFraction, framingPath } from "../lib/crop";
import { clamp, formatTime } from "../lib/time";
import type { Clip, FaceSample, Project, Range } from "../types";

interface Props {
  project: Project;
  clip: Clip;
  range: Range;
  faces: FaceSample[];
  videoRef: RefObject<HTMLVideoElement | null>;
  /** The user placed the 9:16 window at `cx` (0..1) at time `t`. */
  onKeyframe: (t: number, cx: number) => void;
  onResetFraming: () => void;
}

/** The face sample closest to time t, if one is near enough to be "what is on screen now". */
function nearestSample(samples: FaceSample[], t: number): FaceSample | null {
  let best: FaceSample | null = null;
  let bestDistance = 0.36;
  for (const sample of samples) {
    const d = Math.abs(sample.t - t);
    if (d < bestDistance) {
      bestDistance = d;
      best = sample;
    }
  }
  return best;
}

/**
 * Shows the source with the 9:16 window overlaid, next to a live canvas of exactly what the
 * exported vertical clip will look like. Playback loops inside the selected clip.
 * The window can be dragged (or a face clicked while paused) to frame the clip by hand.
 */
export function PreviewPlayer({ project, clip, range, faces, videoRef, onKeyframe, onResetFraming }: Props) {
  const frameRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const windowRef = useRef<HTMLDivElement>(null);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(range.start);

  const cropFrac = cropWidthFraction(project.width, project.height);
  const manual = clip.keyframes.length > 0;
  const path = useMemo(
    () => (manual ? framingPath(clip.keyframes, cropFrac) : project.crop_path),
    [manual, clip.keyframes, project.crop_path, cropFrac],
  );

  // The animation loop below must see fresh values without being torn down and restarted.
  const rangeRef = useRef(range);
  rangeRef.current = range;
  const pathRef = useRef(path);
  pathRef.current = path;
  const dragCx = useRef<number | null>(null); // where the window is while the user holds it
  const grab = useRef<{ offset: number; startX: number; moved: boolean } | null>(null);

  // Once the new framing has arrived from the server, stop overriding the window position.
  useEffect(() => {
    dragCx.current = null;
  }, [clip.keyframes]);

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

        const cx = dragCx.current ?? centerAt(pathRef.current, video.currentTime);
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
  }, [cropFrac, videoRef]);

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

  // --- drag the 9:16 window to frame the clip by hand -------------------------------------------
  const pointerFraction = (e: PointerEvent) => {
    const rect = frameRef.current!.getBoundingClientRect();
    return (e.clientX - rect.left) / rect.width;
  };

  function onWindowDown(e: PointerEvent) {
    const video = videoRef.current;
    if (!video) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    const current = dragCx.current ?? centerAt(pathRef.current, video.currentTime);
    // Remember where inside the window we grabbed it, so it doesn't jump under the pointer.
    grab.current = { offset: pointerFraction(e) - current, startX: e.clientX, moved: false };
  }

  function onWindowMove(e: PointerEvent) {
    const g = grab.current;
    if (!g || (!g.moved && Math.abs(e.clientX - g.startX) < 3)) return;
    if (!g.moved) videoRef.current?.pause(); // precise framing needs a still picture
    g.moved = true;
    dragCx.current = clamp(pointerFraction(e) - g.offset, cropFrac / 2, 1 - cropFrac / 2);
  }

  function onWindowUp() {
    const g = grab.current;
    grab.current = null;
    const video = videoRef.current;
    if (g?.moved && video && dragCx.current !== null) {
      onKeyframe(video.currentTime, dragCx.current); // dragCx is cleared once the saved framing comes back
    } else {
      dragCx.current = null;
      togglePlay(); // a plain click on the window behaves like a click on the video
    }
  }

  const sample = !playing ? nearestSample(faces, time) : null;
  const length = range.end - range.start;
  const position = clamp(time - range.start, 0, length);

  return (
    <div className="player">
      <div className="player-wide">
        <div className="video-frame" ref={frameRef} style={{ aspectRatio: `${project.width} / ${project.height}` }}>
          <video
            ref={videoRef}
            src={api.mediaUrl(project.id)}
            preload="auto"
            playsInline
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
            onClick={togglePlay}
          />
          <div
            className="crop-window"
            ref={windowRef}
            onPointerDown={onWindowDown}
            onPointerMove={onWindowMove}
            onPointerUp={onWindowUp}
            title="Drag to frame the clip yourself"
          />
          {sample?.faces.map((f, i) => (
            <button
              key={i}
              className="face-box"
              style={{
                left: `${(f.cx - f.w / 2) * 100}%`,
                top: `${(f.cy - f.h / 2) * 100}%`,
                width: `${f.w * 100}%`,
                height: `${f.h * 100}%`,
              }}
              aria-label="Follow this face"
              title="Follow this face from here"
              onClick={(e) => {
                e.stopPropagation();
                const t = videoRef.current?.currentTime ?? time;
                onKeyframe(t, clamp(f.cx, cropFrac / 2, 1 - cropFrac / 2));
              }}
            />
          ))}
        </div>

        <p className="muted small">
          {manual ? (
            <>
              Manual framing: {clip.keyframes.length} {clip.keyframes.length === 1 ? "point" : "points"}
              {clip.keyframes.length === 1 && " (one point holds the frame still for the whole clip; add more to move it)"}
              .{" "}
              <button className="link" onClick={onResetFraming}>
                Back to automatic
              </button>
            </>
          ) : project.tracking === "faces" ? (
            "The orange frame follows the speaker. Drag it, or pause and click a face, to frame the clip yourself."
          ) : (
            "No faces found, so the crop stays centred. Drag the orange frame to place it yourself."
          )}
        </p>
        <p className="muted small">Preview is low-res; exports use the original video.</p>
      </div>

      <div className="player-vertical">
        <canvas ref={canvasRef} width={360} height={640} />
        <div className="player-controls">
          <button onClick={togglePlay}>{playing ? "Pause" : "Play clip"}</button>
          <span className="mono">
            {formatTime(position)} / {formatTime(length)}
          </span>
        </div>
      </div>
    </div>
  );
}
