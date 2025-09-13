from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Sequence

from .config import Config


def _is_allowed(path: Path, allowed_exts: Sequence[str]) -> bool:
    try:
        ext = path.suffix.lower()
    except Exception:
        return False
    return ext in allowed_exts


def discover_images(config: Config, exclude_dirs: Iterable[Path] | None = None) -> List[Path]:
    input_dir = config.input_dir
    allowed = config.allowed_extensions
    exclude_dirs = list(exclude_dirs or [])
    # Normalize exclusion by resolving
    exclude_dirs = [p.resolve() for p in exclude_dirs]

    def is_excluded(p: Path) -> bool:
        try:
            rp = p.resolve()
        except Exception:
            rp = p
        for ex in exclude_dirs:
            try:
                if rp.is_relative_to(ex):  # py310+
                    return True
            except AttributeError:
                # Fallback for older versions; not expected on 3.10+
                if str(rp).startswith(str(ex)):
                    return True
        return False

    results: list[Path] = []
    if config.recursive:
        it = input_dir.rglob("*")
    else:
        it = input_dir.glob("*")

    for p in it:
        if not p.is_file():
            continue
        if is_excluded(p):
            continue
        if _is_allowed(p, allowed):
            results.append(p)

    # Deterministic ordering
    results.sort(key=lambda p: str(p).lower())
    return results

