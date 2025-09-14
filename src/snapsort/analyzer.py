from __future__ import annotations

from dataclasses import dataclass
import threading
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, UnidentifiedImageError
import cv2
import imagehash
# typing only used for hints; no runtime cast needed

# Optional RAW (e.g., .nef) decoding via rawpy/LibRaw
try:  # pragma: no cover - optional dependency
    import rawpy  # type: ignore
except Exception:  # pragma: no cover
    rawpy = None  # type: ignore


@dataclass(slots=True)
class AnalysisResult:
    path: Path
    phash: Optional[imagehash.ImageHash]
    blur_variance: Optional[float]
    faces_variances: Optional[list[float]] = None
    error: Optional[str] = None

# Each thread must use its own CascadeClassifier instance — OpenCV's
# CascadeClassifier is not thread-safe when shared. Use thread-local storage.
_TL = threading.local()
_FACE_CASCADE_OVERRIDE_PATH: Optional[str] = None


def set_face_cascade_path(path: Optional[Path]) -> None:
    global _FACE_CASCADE_OVERRIDE_PATH
    _FACE_CASCADE_OVERRIDE_PATH = str(path) if path is not None else None
    # Reset any thread-local cached classifier so new path takes effect
    try:
        _TL.cascade = None  # type: ignore[attr-defined]
    except Exception:
        pass


def _get_face_cascade() -> Optional[cv2.CascadeClassifier]:
    # Return a per-thread CascadeClassifier instance. Creating the classifier
    # is cheap compared to I/O, and avoids crashes from sharing across threads.
    try:
        cascade = getattr(_TL, "cascade", None)
    except Exception:
        cascade = None
    if cascade is not None:
        return cascade
    try:
        # Use override if provided, else built-in OpenCV haarcascades path
        if _FACE_CASCADE_OVERRIDE_PATH:
            cascade_path = _FACE_CASCADE_OVERRIDE_PATH
        else:
            cascade_path = str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
        cascade = cv2.CascadeClassifier(cascade_path)
        if cascade.empty():
            return None
        _TL.cascade = cascade
        return cascade
    except Exception:
        return None


def _load_image_rgb(path: Path) -> Image.Image:
    """Load an image as RGB. Supports camera RAW like .nef when rawpy is available.

    For RAW files (.nef), we use rawpy to decode and postprocess into an 8-bit
    RGB numpy array, then convert to a PIL Image. For standard formats, fall
    back to Pillow.
    """
    suffix = path.suffix.lower()
    is_raw_nef = suffix == ".nef"
    if is_raw_nef and rawpy is None:  # type: ignore[name-defined]
        raise RuntimeError("RAW (.nef) support requires 'rawpy'. Install with: pip install rawpy")
    if is_raw_nef and rawpy is not None:  # type: ignore[name-defined]
        try:
            with rawpy.imread(str(path)) as raw:  # type: ignore[attr-defined]
                rgb = raw.postprocess(
                    use_auto_wb=True,
                    no_auto_bright=True,
                    output_bps=8,
                    gamma=(2.2, 4.5),
                )
            # rgb is HxWx3 uint8
            return Image.fromarray(rgb, mode="RGB")
        except Exception as e:
            # Fall back to Pillow path below which will likely error if not supported
            last_err = e
    # Standard path via Pillow
    with Image.open(path) as img:
        return img.convert("RGB")


def analyze_image(path: Path, *, do_face_analysis: bool = True) -> AnalysisResult:
    try:
        img = _load_image_rgb(path)
        # Compute pHash
        ph = imagehash.phash(img)
        # Convert to grayscale numpy for blur metric
        arr = np.array(img)
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        variance = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        faces_variances: Optional[list[float]] = None
        if do_face_analysis:
            faces_variances = []
            cascade = _get_face_cascade()
            if cascade is not None:
                # Detect faces; tune params for reasonable recall/precision
                faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
                for (x, y, w, h) in faces:
                    roi = gray[y : y + h, x : x + w]
                    fv = float(cv2.Laplacian(roi, cv2.CV_64F).var())
                    faces_variances.append(fv)
            else:
                faces_variances = []
        return AnalysisResult(path=path, phash=ph, blur_variance=variance, faces_variances=faces_variances)
    except (UnidentifiedImageError, OSError) as e:
        return AnalysisResult(path=path, phash=None, blur_variance=None, error=str(e))
    except Exception as e:  # Be resilient to unexpected decoder errors
        return AnalysisResult(path=path, phash=None, blur_variance=None, error=str(e))
