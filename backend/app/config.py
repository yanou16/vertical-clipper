"""Central configuration. Everything can be overridden with environment variables."""
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent

DATA_DIR = Path(os.environ.get("CLIPPER_DATA_DIR", ROOT_DIR / "data"))
PROJECTS_DIR = DATA_DIR / "projects"
MODEL_PATH = BACKEND_DIR / "models" / "face_detection_yunet_2023mar.onnx"
FRONTEND_DIST = Path(os.environ.get("CLIPPER_FRONTEND_DIST", ROOT_DIR / "frontend" / "dist"))

# Input limits (protect the machine of a non-technical user from huge files).
MAX_UPLOAD_MB = int(os.environ.get("CLIPPER_MAX_UPLOAD_MB", "4096"))
MAX_VIDEO_MINUTES = int(os.environ.get("CLIPPER_MAX_VIDEO_MINUTES", "180"))
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}

# YouTube download quality = maximum video height we are willing to fetch.
# A 9:16 crop only uses a slice of the width, so a sharper source gives a visibly sharper clip.
QUALITY_CHOICES = (720, 1080, 1440, 2160)
DEFAULT_QUALITY = 1440

# Output format.
OUT_WIDTH, OUT_HEIGHT = 1080, 1920

# Analysis: how often we look at the video (frames per second sampled).
ANALYSIS_FPS = 4
ANALYSIS_WIDTH = 640

# Segmentation defaults (seconds).
DEFAULT_TARGET_LEN = 30.0
DEFAULT_MIN_LEN = 15.0
DEFAULT_MAX_LEN = 60.0

# Clip editing limits (seconds).
CLIP_MIN_LEN = 1.0
CLIP_MAX_LEN = 180.0

WORKER_THREADS = int(os.environ.get("CLIPPER_WORKERS", "2"))

# A video interrupted by a server restart is resumed automatically this many times, then marked as failed
# (protects against a video that crashes the server over and over).
MAX_RECOVERY_ATTEMPTS = 2
