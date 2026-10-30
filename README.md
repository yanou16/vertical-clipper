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

**Prefer Docker?** Nothing else to install:

```bash
docker compose up --build
```

then open <http://localhost:8000> (`CLIPPER_PORT=8001 docker compose up --build` to use another port). Projects and
exports are kept in a Docker volume, so they survive restarts; `docker compose down -v` deletes them.
Tested on macOS (Docker Desktop, Apple silicon): the image builds, a YouTube link downloaded at 4K is analysed and
exported, an uploaded file works, and data survives a restart. I have not run it on Linux or Windows.

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

### Sharper clips: download quality

A vertical clip only uses a slice of the picture (608×1080 pixels out of a 1080p frame) that is then enlarged to
1080×1920, so the **source resolution matters a lot**.

- Pick the quality next to the YouTube link: 4K, 1440p (default), 1080p or 720p. For each choice the tool takes the
  stream with the **highest bitrate** up to that height. (yt-dlp's default favours the newest codec even when it is the
  most compressed one: on a test video it picked AV1 at 498 kb/s over H.264 at 1,022 kb/s at the same 1080p.)
- The editor shows what the original really is (resolution, codec, bitrate) and by how much the clips are enlarged.
  A 4K source is *reduced* to 1080×1920 instead of enlarged. On a 16-second 4K test video this gave a visibly
  **cleaner** picture (no enlargement halos around bright details, finer lines), not a dramatically sharper one:
  how much you gain depends on the content. A plain "sharpness" metric even scored the enlarged 1080p version
  higher, because enlarging adds edge artefacts that the metric counts as detail, so judge by eye.
- Higher quality means a bigger download and slower exports. Measured on a 16 s test video: the 4K stream is 22 MB
  (11.7 Mb/s) against 3.5 MB at 1080p, and the clip exports in 6.6 s against 4.6 s. A 1-hour 4K video is several GB,
  so on a slow connection (mine ran at roughly 150-350 KB/s) it can take hours: start with 1080p or 1440p.
- **Lighter download** (checkbox under the link): same height cap, but it prefers 30 fps or less and the VP9 codec,
  which gives much smaller files. On a 10-minute 720p video the normal pick (50 fps H.264) is 210 MB, while the lighter
  one would be about 75 MB (sizes from YouTube's own format list; I ran the lighter mode end to end only on a short test
  video). Little is lost for talking-head content; fast sport will look a bit less smooth.
- **Where the time goes**, measured on that 10-minute video over a slow connection (about 100-300 KB/s): download
  16 min 56 s (92 % of the wait), 480p preview 1 min 21 s, analysis 11 s. The progress screen shows the percentage,
  the size, the speed and the time left while downloading.
- YouTube hides some formats behind a small JavaScript puzzle. The tool installs `yt-dlp-ejs` (from the yt-dlp
  project) and uses whichever JavaScript runtime you have (deno, node or bun).

### Frame a clip yourself

The automatic camera follows the main face. To override it for one clip:

- **drag the orange frame** on the wide preview to where you want it, or **pause and click a face** to follow it from
  that moment on;
- each placement is a *framing point* (a diamond on the timeline); the camera glides between points. One point holds the
  frame still for the whole clip. **Back to automatic** removes them.

### Long jobs are safe to interrupt

- If the server stops or crashes while a video is processing or exporting, the work **resumes automatically** on the
  next start (a video that keeps crashing it is marked as failed after two attempts).
- A failed video has a **Try again** button; a finished download is reused, not downloaded twice.
- Exports can be **cancelled** one by one or all at once, and you can tick several clips and **export just those**.

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

- Tracks one main subject automatically; with several people you pick who to follow by hand. Next step: switch
  automatically to whoever speaks (using audio activity) or a split-screen layout for two-person interviews.
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
