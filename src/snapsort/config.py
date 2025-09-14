from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Tuple


def _parse_extensions(exts: str | Iterable[str]) -> Tuple[str, ...]:
    if isinstance(exts, str):
        parts = [e.strip() for e in exts.split(",") if e.strip()]
    else:
        parts = [str(e).strip() for e in exts]
    norm = []
    for e in parts:
        if not e:
            continue
        e = e.lower()
        if not e.startswith("."):
            e = "." + e
        norm.append(e)
    return tuple(dict.fromkeys(norm))


@dataclass(slots=True)
class Config:
    input_dir: Path
    duplicate_threshold: int = 5
    blur_threshold: float = 100.0
    blur_folder_name: str = "blurred"
    partial_blur_folder_name: str = "partialBlurred"
    slight_blur_folder_name: str = "slightlyBlurred"
    duplicate_folder_name: str = "duplicate"
    # Include .nef (Nikon RAW) by default; additional RAWs can be added via --extensions
    allowed_extensions: Tuple[str, ...] = (".jpg", ".jpeg", ".nef")
    recursive: bool = True
    dry_run: bool = False
    max_workers: int | None = None
    log_level: str = "INFO"
    output_dir: Path | None = None
    keep_originals: bool = False
    prefer_duplicate_over_blur: bool = True
    # Blur target: 'faces' or 'image'. For this project default to 'faces'.
    blur_on: str = "faces"
    # Partial blur threshold (percent of faces blurred to qualify as partial)
    partial_blur_min_percent: float = 50.0
    # Optional override for face cascade path; if None, use OpenCV builtin
    face_cascade_path: Path | None = None

    @property
    def base_output_dir(self) -> Path:
        return self.output_dir or self.input_dir

    @classmethod
    def from_args(cls, args) -> "Config":  # args: argparse.Namespace
        input_dir = Path(args.input_dir).expanduser().resolve()
        if not input_dir.exists() or not input_dir.is_dir():
            raise SystemExit(f"Input directory not found: {input_dir}")

        allowed_extensions = (
            _parse_extensions(args.extensions)
            if getattr(args, "extensions", None)
            else cls.allowed_extensions
        )

        output_dir = (
            Path(args.output_dir).expanduser().resolve() if getattr(args, "output_dir", None) else None
        )

        face_cascade_path = (
            Path(args.face_cascade).expanduser().resolve() if getattr(args, "face_cascade", None) else None
        )

        return cls(
            input_dir=input_dir,
            duplicate_threshold=int(args.duplicate_threshold),
            blur_threshold=float(args.blur_threshold),
            blur_folder_name=str(args.blur_folder),
            partial_blur_folder_name=str(getattr(args, "partial_blur_folder", "partialBlurred")),
            slight_blur_folder_name=str(getattr(args, "slight_blur_folder", "slightlyBlurred")),
            duplicate_folder_name=str(args.duplicate_folder),
            allowed_extensions=allowed_extensions,
            recursive=bool(args.recursive),
            dry_run=bool(args.dry_run),
            max_workers=(int(args.max_workers) if args.max_workers is not None else None),
            log_level=str(args.log_level).upper(),
            output_dir=output_dir,
            keep_originals=bool(args.keep_originals),
            prefer_duplicate_over_blur=True,  # MVP default; could be exposed later
            blur_on=str(getattr(args, "blur_on", "faces")).lower(),
            partial_blur_min_percent=float(getattr(args, "partial_blur_min_percent", 50.0)),
            face_cascade_path=face_cascade_path,
        )
