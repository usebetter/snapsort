# Build Task: **snapSort** – Python image organizer (MVP)

## Goal
Create a Python project called **snapSort** that reorganizes `.jpg`/`.jpeg` images in a given directory into subfolders based on analysis:

- **Blurred** images → moved to a folder named from config (default `"blurred"`).
- **Duplicate / near-duplicate** images → moved to a folder named from config (default `"duplicate"`).

The script must be parameterized via a **Config** class (no hardcoded values). All thresholds, folder names, file extensions, recursion behavior, etc., come from this config and/or CLI args that populate/override the config.

## Functional Requirements

1. **CLI**
   - Command: `python -m snapsort` or `python snapsort.py`
   - Required argument: `--input-dir` (path to directory containing images)
   - Optional args (override config defaults):
     - `--duplicate-threshold` (int) – Hamming distance threshold for near-duplicate detection.
     - `--blur-threshold` (float) – Variance of Laplacian threshold below which an image is considered blurred.
     - `--blur-folder` (str) – target folder name for blurred images.
     - `--duplicate-folder` (str) – target folder name for duplicates.
     - `--extensions` (str, comma-separated) – allowed extensions (default: .jpg,.jpeg).
     - `--recursive` (flag) – include subdirectories.
     - `--dry-run` (flag) – show planned moves but don’t modify files.
     - `--max-workers` (int) – parallelism for hashing/blur checks.
     - `--log-level` (str) – DEBUG/INFO/WARN/ERROR.
     - `--output-dir` (optional) – base output directory; if omitted, use the input directory as base for creating target folders.
     - `--keep-originals` (flag) – copy instead of move (default is move).

2. **Config Class**
   - A single `Config` class (e.g., `snapsort/config.py`) encapsulating **all** tunables:
     - `duplicate_threshold: int` (default e.g., 5)
     - `blur_threshold: float` (default e.g., 100.0)
     - `blur_folder_name: str` (default `"blurred"`)
     - `duplicate_folder_name: str` (default `"duplicate"`)
     - `allowed_extensions: tuple[str, ...]` (default `(".jpg", ".jpeg")`)
     - `recursive: bool` (default `True`)
     - `dry_run: bool` (default `False`)
     - `max_workers: int | None`
     - `log_level: str` (default `"INFO"`)
     - `output_dir: Path | None`
     - `keep_originals: bool` (default `False`)
   - Provide a factory method to construct from CLI args and environment.
   - **No hardcoded literals** in the logic—everything should reference `Config`.

3. **Image Analysis**
   - **Duplicate detection**:
     - Use **perceptual hashing** (pHash) via `imagehash` with `Pillow`.
     - Maintain a mapping of hash → list of file paths.
     - Consider near-duplicates using Hamming distance ≤ `duplicate_threshold`.
     - For near-duplicate grouping, ensure deterministic selection of the “kept” original (e.g., first encountered or largest file size) and move the rest to duplicate folder.
   - **Blur detection**:
     - Use **OpenCV** (`cv2`) to compute **variance of Laplacian** for focus measure.
     - If variance < `blur_threshold`, classify as blurred.

4. **Processing Flow**
   - Discover images by walking `input_dir` (respect `recursive`, `allowed_extensions`).
   - Compute pHash (and store) + compute blur metric for each image.
   - Decide moves:
     - If image is blurred → move/copy to `blur_folder`.
     - If image is duplicate/near-duplicate of a previously seen image → move/copy to `duplicate_folder`.
     - If an image qualifies for both, put it in **both**? For MVP, prioritize **duplicate** first (configurable via a boolean `prefer_duplicate_over_blur: bool = True`). If set, duplicates win; else blurred wins.
   - Actually **create** target folders if they don’t exist (under `output_dir` or `input_dir` base).
   - On `--dry-run`, print planned operations only.
   - Preserve filename; on collision, append a short suffix (e.g., `_1`, `_2`) before extension.

5. **Logging & UX**
   - Use `logging` or `rich` for colored logs (configurable by `log_level`).
   - Show a progress bar (e.g., `tqdm`) during scanning and processing.
   - Emit a final summary:
     - Total images scanned
     - # blurred moved
     - # duplicates moved (and how many groups)
     - # errors (if any)

6. **Reliability**
   - Handle unreadable/corrupt images gracefully (log warning, skip).
   - Normalize file extension case.
   - Make operations idempotent—re-running shouldn’t crash.
   - Support large folders (use streaming/iterative processing and optional concurrency).

## Project Layout

```
snapSort/
├─ README.md
├─ requirements.txt
├─ pyproject.toml            # or setup.cfg; minimal metadata + entry point
├─ src/
│  └─ snapsort/
│     ├─ __init__.py
│     ├─ cli.py              # argparse/typer CLI, builds Config and runs
│     ├─ config.py           # Config class + from_args
│     ├─ analyzer.py         # pHash + blur metric utilities
│     ├─ mover.py            # safe move/copy utilities (collision handling)
│     ├─ scanner.py          # file discovery
│     └─ runner.py           # orchestrates pipeline
└─ tests/ (optional for MVP)
   ├─ test_config.py
   ├─ test_analyzer.py
   └─ test_runner.py
```

- Provide a console script entry point: `snapsort` → `snapsort.cli:main`.

## Implementation Details & Acceptance Criteria

- **Hashing**: use `imagehash.phash(Image.open(path))`. Store as `ImageHash`.
- **Near-duplicate logic**:
  - Maintain a list of representative hashes.
  - For a new image, compute min Hamming distance to representatives. If ≤ threshold, mark as duplicate of that group; otherwise, new representative.
  - Keep first file (or largest size) as canonical; move subsequent ones.
  - Implement Hamming distance via `ImageHash - ImageHash`.
- **Blur metric**: `variance = cv2.Laplacian(gray, cv2.CV_64F).var()`.
- **Performance**:
  - Use a `ThreadPoolExecutor` with `max_workers` for reading + hashing + blur.
  - Avoid loading an image twice; compute both metrics in a single read.
- **Moving/Copying**:
  - Default **move**. If `keep_originals=True`, **copy** instead.
  - Ensure folders are created under `output_dir or input_dir`.
  - Resolve name collisions deterministically with suffixes.
- **OS Support**: Windows/macOS/Linux (use `pathlib`).
- **Python Version**: 3.10+.

## README.md (include this content)

- **Overview**: What snapSort does, how duplicates and blur are detected (short explanation).
- **Requirements**: Python 3.10+.
- **Installation**:
  ```bash
  python -m venv .venv
  source .venv/bin/activate  # Windows: .venv\Scripts\activate
  pip install -r requirements.txt
  pip install -e .           # if pyproject.toml provides entry point
  ```
- **Usage**:
  ```bash
  snapsort --input-dir /path/to/photos
  ```
  Common options:
  ```bash
  snapsort     --input-dir /path/to/photos     --duplicate-threshold 5     --blur-threshold 100.0     --blur-folder blurred     --duplicate-folder duplicate     --extensions .jpg,.jpeg     --recursive     --output-dir /path/to/output     --max-workers 8     --dry-run
  ```
- **How it works**:
  - Duplicate detection via perceptual hashing (pHash) with configurable Hamming-distance threshold.
  - Blur detection via variance of Laplacian with configurable threshold.
  - Priority between duplicate vs blurred controlled by config flag.
- **Notes**:
  - Large folders supported; uses concurrency.
  - `--dry-run` prints planned moves without changing files.
- **Troubleshooting**:
  - If OpenCV fails to read certain images, ensure file is not corrupt and that `opencv-python` is installed (not `opencv-contrib-python` unless needed).
  - On Windows paths, quote arguments containing spaces.

## requirements.txt
Use minimal, widely available dependencies:

```
Pillow>=10.0.0
imagehash>=4.3.1
opencv-python>=4.9.0.0
numpy>=1.26.0
tqdm>=4.66.0
rich>=13.7.0
typer>=0.12.0   # or use argparse; if using argparse, omit this line
```

> If you choose `argparse`, remove `typer` and implement the same CLI flags.

## Developer Notes
- Write clean, typed code (use `from __future__ import annotations` and type hints).
- Separate concerns across `scanner.py`, `analyzer.py`, `mover.py`, `runner.py`.
- Add docstrings and inline comments explaining any non-obvious logic.
- Return non-zero exit code on fatal errors (e.g., input dir not found).

## Deliverables
1. Complete project in the specified structure.
2. Fully working CLI as `snapsort`.
3. `requirements.txt` with all dependencies.
4. `README.md` with installation and usage instructions.
5. (Optional) Basic tests for analyzer and config.

**Definition of Done**: Running `snapsort --input-dir <folder>` on a directory of JPG/JPEG images results in all blurred images moved to the configured blurred folder and all duplicates/near-duplicates moved to the configured duplicate folder, with progress logs and a final summary; no values hardcoded outside the `Config` class; CLI options override config.
