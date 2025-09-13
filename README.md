snapSort — Python image organizer (MVP)

Overview
- Organizes .jpg/.jpeg images by moving or copying them into subfolders based on analysis.
- Duplicate/near-duplicate detection via perceptual hashing (pHash) from imagehash/Pillow.
- Blurred detection via variance of Laplacian (OpenCV) with a configurable threshold.
- Priority between duplicate vs blurred classification is configurable.

Requirements
- Python 3.10+

Installation
- Create and activate a virtual environment, then install requirements and the package:

  bash
  python -m venv .venv
  source .venv/bin/activate  # Windows: .venv\Scripts\activate
  pip install -r requirements.txt
  pip install -e .

Usage
- Basic:

  bash
  snapsort --input-dir /path/to/photos

- Common options:

  bash
  snapsort \
    --input-dir /path/to/photos \
    --duplicate-threshold 5 \
    --blur-threshold 100.0 \
    --blur-folder blurred \
    --partial-blur-folder partialBlurred \
    --slight-blur-folder slightlyBlurred \
    --duplicate-folder duplicate \
    --extensions .jpg,.jpeg \
    --recursive \
    --output-dir /path/to/output \
    --max-workers 8 \
    --blur-on faces \
    --partial-blur-min-percent 50 \
    --dry-run

How it works
- Duplicate detection via perceptual hashing (pHash) with a Hamming-distance threshold.
- Blur detection via variance of Laplacian with a configurable threshold.
- Face-aware blur: with `--blur-on faces` (default), blur decisions are based on human faces only:
  - 100% faces blurred → moved to `--blur-folder`.
  - 50–99% faces blurred → moved to `--partial-blur-folder` (min percent configurable).
  - 1–49% faces blurred → moved to `--slight-blur-folder`.
  - 0 faces detected → no face-blur action.
- Config flag `prefer_duplicate_over_blur` controls which classification wins when both apply.
- Uses concurrency for performance and a progress bar during analysis.

Notes
- Large folders supported; uses a ThreadPoolExecutor with optional `--max-workers`.
- `--dry-run` prints planned operations without changing files.

Troubleshooting
- If OpenCV fails to read certain images, ensure files aren’t corrupt and that `opencv-python` is installed.
- On Windows paths, quote arguments containing spaces.
