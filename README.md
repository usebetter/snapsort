snapSort — Python image organizer (MVP)

Overview
- Organizes .jpg/.jpeg (and optionally RAW like .nef) images by moving or copying them into subfolders based on analysis.
- Duplicate/near-duplicate detection via perceptual hashing (pHash) from imagehash/Pillow.
- Blurred detection via variance of Laplacian (OpenCV) with a configurable threshold.
- Priority between duplicate vs blurred classification is configurable.

Binary Downloads (macOS)
- Download prebuilt archives from GitHub Releases:
  - Latest: https://github.com/usebetter/snapsort/releases/latest
  - Choose the archive for your Mac:
    - `snapsort-macos-arm64.7z` → Apple Silicon (M1/M2/M3)
    - `snapsort-macos-x86_64.7z` → Intel Macs
- Extract the 7z (Finder with The Unarchiver/KEKA or `7z x snapsort-macos-*.7z`).
- Run from Terminal:
  - `cd <extracted>/`
  - `./snapsort --help`
- If macOS blocks the app (Gatekeeper):
  - Right-click the `snapsort` binary → Open (confirm once), or
  - `xattr -dr com.apple.quarantine <extracted-folder>`
- Notes:
  - These bundles include Python and dependencies (no separate install needed).
  - For Intel on Apple Silicon, use the x86_64 build only if you specifically need it.

Requirements
- Python 3.10+

Installation
- Create and activate a virtual environment, then install requirements and the package:

  bash
  python -m venv .venv
  source .venv/bin/activate  # Windows: .venv\Scripts\activate
  pip install -r requirements.txt
  pip install -e .

RAW support (.nef)
- The tool can analyze Nikon RAW `.nef` files. Install the optional decoder:

  bash
  pip install rawpy

- Then include `.nef` in extensions (default already includes it):

  bash
  snapsort --input-dir /path --extensions .jpg,.jpeg,.nef

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
    --extensions .jpg,.jpeg,.nef \
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
- If RAW files (.nef) are skipped, ensure `rawpy` is installed; otherwise add `--extensions` to exclude `.nef`.
- On Windows paths, quote arguments containing spaces.
