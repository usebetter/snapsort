from __future__ import annotations

from dataclasses import dataclass
import threading
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, UnidentifiedImageError
import cv2
import imagehash


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


def analyze_image(path: Path, *, do_face_analysis: bool = True) -> AnalysisResult:
    try:
        with Image.open(path) as img:
            img = img.convert("RGB")
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
