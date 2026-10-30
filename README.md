# Vertical Clipper

Turn long **16:9 videos** (a YouTube link or an uploaded file) into **9:16 vertical clips** for Shorts / Reels / TikTok.
The tool finds natural clip boundaries, keeps the speaker in frame with face tracking (no dumb centre crop), lets you
fine-tune every clip, and exports them one by one or all at once.

100% free and open source: **FFmpeg · Python · FastAPI · OpenCV (YuNet face detector) · yt-dlp · React**.
Everything runs on your own computer, nothing is sent to any paid service.

## Quick start (no coding needed)

You need **FFmpeg**, **Python 3.10+** and **Node.js 18+** (Node is only used once, to build the web page).

| OS | Install FFmpeg | Then |
|----|---------------|------|
| macOS | `brew install ffmpeg` | `./start.sh` |
| Linux | `sudo apt install ffmpeg` | `./start.sh` |
| Windows | `winget install ffmpeg` | double-click `start.bat` |

The script installs everything else, starts the app and opens <http://localhost:8000>.
First launch takes about a minute; the next ones are instant. Press `Ctrl+C` to stop.

**Prefer Docker?** Nothing else to install. (`start.sh` is the path I tested end to end; the Docker image is provided
as an alternative and I have not yet completed a successful build of it. Please report any issue.)

```bash
docker compose up --build
```

then open <http://localhost:8000>. Projects and exports are kept in `./data`.

## How to use it

1. **Add a video**: paste a YouTube link, or drop a video file (MP4, MOV, MKV, WebM…).
2. **Wait a moment**: the tool downloads it, makes a light preview, then looks for the best moments and tracks faces.
3. **Review the clips** on the right. Click one to edit it:
   - the left preview shows the wide video with a bright frame (the vertical window that follows the speaker);
   - the right preview shows exactly what the vertical clip will look like;
   - **drag the handles** on the timeline (or use the Start / End boxes and ±1s buttons) to move where the clip
     starts and ends; **Shorter / Longer** buttons extend or cut it by 5s or 1s; drag the middle to slide the whole clip;
   - rename it, delete it, or **add a clip at the playhead**; **Re-split** redoes the automatic split with another length.
4. **Export**: *Export* on a single clip, or *Export all*, then *Download* each file or the *ZIP* with everything.
   If you change a clip after exporting it, it is flagged for re-export automatically.

Output: `1080×1920`, H.264 + AAC, MP4 (plays everywhere, ready to upload).

## How it works

```
 YouTube URL ──yt-dlp──┐
                       ├─► source.mp4 ─► ffprobe ─► 480p proxy (browser preview)
 uploaded file ────────┘                                 │
                                                         ▼
                       one pass @ 4 fps:  shot changes (colour histograms)
                                          faces (OpenCV YuNet)             silences (ffmpeg)
                                                         │
                          ┌──────────────────────────────┴───────────────┐
                          ▼                                              ▼
                 segmentation → clips                      camera path (x over time)
        (≈30s, cut on a shot change or a pause)     follow subject · dead zone · jump on cuts
                                                                         │
 export = ffmpeg decode ─► OpenCV crop 9:16 following the path ─► ffmpeg encode (+ original audio)
```

Design choices worth knowing:

- **Analyse once, edit freely.** Face tracking runs on the whole video at import time, so moving or extending a clip
  never needs re-analysis and the editor preview is instant.
- **A virtual camera, not a per-frame crop.** The crop follows the main face (largest, sticky to the same person)
  but ignores small movements (dead zone), eases towards big ones, and *jumps* with shot changes instead of gliding across
  a cut. Static shots stay perfectly still, which looks far more professional than a jittery follow.
- **Natural boundaries.** Clips aim for ~30s but snap to the nearest shot change or pause in the audio, so you rarely
  cut a sentence in half. If nothing natural is nearby it cuts at the target length.
- **Preview ≠ export quality.** The editor plays a light 480p proxy so it stays fast with any input codec; exports are
  made from the original full-quality file.
- **No faces? No problem.** If faces are found in too few frames (screen recordings, landscapes) it falls back to a
  centred crop and says so in the editor.
- **Simple and robust storage.** One folder + one JSON file per project (atomic writes), a small thread pool for jobs.
  The browser polls once per second. No database or queue to install.

## Project layout

```
backend/app
  main.py            FastAPI app (also serves the built React app)
  config.py          paths, limits, defaults (env-overridable)
  models.py          Pydantic models + request validation
  store.py           file-based project store
  jobs.py            background pipeline (ingest → analyse → segment) and exports
  routers/projects.py  HTTP API
  services/
    ingest.py        yt-dlp download, upload checks
    media.py         ffprobe / ffmpeg helpers, silence detection
    analysis.py      shot changes + face detection in one pass
    segmentation.py  pure function: durations + candidate cut points → clips
    tracking.py      detections → smooth camera path
    render.py        crop + encode one clip
backend/tests        pytest suite (segmentation, tracking, API validation)
frontend/src         React + TypeScript (Vite): components/, lib/, api.ts
```

## Development

```bash
# terminal 1: API on :8000
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m uvicorn app.main:app --reload
# terminal 2: UI on :5173 with hot reload (proxies /api to :8000)
cd frontend && npm install && npm run dev
# tests
cd backend && .venv/bin/python -m pytest
```

Settings (environment variables): `CLIPPER_DATA_DIR`, `CLIPPER_MAX_UPLOAD_MB` (default 4096),
`CLIPPER_MAX_VIDEO_MINUTES` (default 180), `CLIPPER_WORKERS` (parallel exports, default 2).

## Limits & what I'd do next

- Tracks one main subject. Next step: two-person interviews (split-screen or switching to whoever speaks, using
  audio activity) and a manual "pin the crop here" override per clip.
- Segmentation is audio/visual only. Next step: transcribe with an open-source model (Whisper) to cut on sentence
  boundaries and pick the most engaging segments; burn in captions.
- The server is built for **one user on a local machine** and binds to `127.0.0.1` with no login. To put it online it
  would need authentication, per-user storage, a real job queue (Celery/RQ + Redis) and cleanup of old projects
  (see the production-readiness notes in my written review).
- Downloading from YouTube relies on `yt-dlp`; keep it updated (`pip install -U yt-dlp`) if downloads start failing,
  and only use videos you have the rights to.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "ffmpeg not found" | Install FFmpeg (table above) and restart the app. |
| A YouTube link fails | Make sure the video is public, then run `backend/.venv/bin/pip install -U yt-dlp`. |
| Crop stays centred | No faces were detected (see the note under the preview). Face tracking needs visible faces. |
| Export is slow | It renders in full quality; 4K sources take longer. Lower `CLIPPER_WORKERS` on small machines. |

## Credits & licences

[FFmpeg](https://ffmpeg.org) (LGPL/GPL), [OpenCV](https://opencv.org) (Apache-2.0) and its
[YuNet face detector](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet) (MIT, model file in
`backend/models/`), [yt-dlp](https://github.com/yt-dlp/yt-dlp) (Unlicense), FastAPI (MIT), React (MIT).
