from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class MovePlan:
    src: Path
    dest: Path
    reason: str  # "duplicate" or "blurred"


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def unique_destination(dest_dir: Path, filename: str) -> Path:
    base = Path(filename).stem
    ext = Path(filename).suffix
    candidate = dest_dir / f"{base}{ext}"
    i = 1
    while candidate.exists():
        candidate = dest_dir / f"{base}_{i}{ext}"
        i += 1
    return candidate


def move_or_copy(plan: MovePlan, copy: bool = False) -> Path:
    ensure_dir(plan.dest.parent)
    if plan.dest.exists():
        plan = MovePlan(src=plan.src, dest=unique_destination(plan.dest.parent, plan.dest.name), reason=plan.reason)
    if copy:
        return Path(shutil.copy2(plan.src, plan.dest))
    else:
        return Path(shutil.move(plan.src, plan.dest))

