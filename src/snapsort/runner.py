from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from tqdm import tqdm
import imagehash

from .config import Config
from .scanner import discover_images
from .analyzer import analyze_image, AnalysisResult, set_face_cascade_path
from .mover import MovePlan, ensure_dir, move_or_copy


logger = logging.getLogger("snapsort")


@dataclass(slots=True)
class DupGroup:
    rep_hash: imagehash.ImageHash
    canonical_index: int
    canonical_path: Path
    members: List[int]


def _group_duplicates(results: List[AnalysisResult], threshold: int) -> Tuple[List[DupGroup], Dict[Path, bool]]:
    groups: List[DupGroup] = []
    duplicate_map: Dict[Path, bool] = {}

    for idx, res in enumerate(results):
        if res.phash is None:
            continue
        # Find nearest representative
        min_dist = None
        min_gi = None
        for gi, g in enumerate(groups):
            dist = g.rep_hash - res.phash
            if min_dist is None or dist < min_dist:
                min_dist = dist
                min_gi = gi
        if min_dist is None or min_dist > threshold:
            # Create new group with this as canonical
            groups.append(DupGroup(rep_hash=res.phash, canonical_index=idx, canonical_path=res.path, members=[idx]))
        else:
            g = groups[min_gi]
            g.members.append(idx)
            # Only non-canonical members are duplicates
            duplicate_map[res.path] = True

    return groups, duplicate_map


def run(config: Config) -> int:
    # Determine base and excluded directories to prevent re-processing moved files
    base_output = config.base_output_dir
    blur_dir = base_output / config.blur_folder_name
    partial_blur_dir = base_output / config.partial_blur_folder_name
    slight_blur_dir = base_output / config.slight_blur_folder_name
    dup_dir = base_output / config.duplicate_folder_name
    exclude = []
    # Only exclude if they are within the input directory
    for d in (blur_dir, partial_blur_dir, slight_blur_dir, dup_dir):
        try:
            if d.resolve().is_relative_to(config.input_dir.resolve()):
                exclude.append(d)
        except AttributeError:
            # py310+ has is_relative_to; safeguard for compatibility
            if str(d.resolve()).startswith(str(config.input_dir.resolve())):
                exclude.append(d)

    # Configure face cascade if provided
    if config.face_cascade_path is not None:
        try:
            set_face_cascade_path(config.face_cascade_path)
        except Exception:
            logger.warning("Failed to set custom face cascade path: %s", config.face_cascade_path)

    # Preflight permission checks to fail early instead of after long analysis
    def _writable_for_create_or_write(p: Path) -> bool:
        try:
            if p.exists():
                return os.access(p, os.W_OK | os.X_OK)
            parent = p.parent if p.parent.exists() else p.parent
            return os.access(parent, os.W_OK | os.X_OK)
        except Exception:
            return False

    base_target = config.base_output_dir
    if not config.dry_run:
        if not _writable_for_create_or_write(base_target):
            logger.error(
                "Output directory is not writable: %s. Use --output-dir to a writable location or fix permissions.",
                base_target,
            )
            logger.error(
                "Tip: On macOS, you may need to grant Terminal Full Disk Access if targeting Desktop/Downloads."
            )
            raise SystemExit(2)
        if not config.keep_originals:
            # Moving requires permission to remove from the input directory
            if not os.access(config.input_dir, os.W_OK | os.X_OK):
                logger.error(
                    "Input directory is not writable for moving files: %s. Either fix permissions or use --keep-originals or choose a different --output-dir.",
                    config.input_dir,
                )
                raise SystemExit(2)

    paths = discover_images(config, exclude_dirs=exclude)
    total = len(paths)
    if total == 0:
        logger.info("No images found in %s matching extensions %s", config.input_dir, config.allowed_extensions)
        return 0

    logger.info("Scanning %d images...", total)

    results_by_path: Dict[Path, AnalysisResult] = {}

    with ThreadPoolExecutor(max_workers=config.max_workers) as ex:
        futures = {ex.submit(analyze_image, p, do_face_analysis=(config.blur_on == "faces")): p for p in paths}
        for fut in tqdm(as_completed(futures), total=total, desc="Analyzing", unit="img"):
            p = futures[fut]
            try:
                res = fut.result()
            except Exception as e:  # Defensive: shouldn't normally happen
                res = AnalysisResult(path=p, phash=None, blur_variance=None, error=str(e))
            results_by_path[p] = res

    # Preserve deterministic order: same as paths
    results: List[AnalysisResult] = [results_by_path[p] for p in paths]

    error_count = sum(1 for r in results if r.error)
    if error_count:
        logger.warning("Encountered %d errors while reading images; they will be skipped.", error_count)

    # Optional: print successfully scanned files grouped by extension
    if config.print_scanned:
        ok = [r for r in results if not r.error]
        by_ext: Dict[str, List[Path]] = {}
        for r in ok:
            ext = r.path.suffix.lower()
            by_ext.setdefault(ext, []).append(r.path)
        if config.print_format == "csv":
            logger.info("ext,path")
            for ext, paths_ext in sorted(by_ext.items()):
                for p in paths_ext:
                    logger.info("%s,%s", ext, p)
        else:
            for ext, paths_ext in sorted(by_ext.items()):
                logger.info("Scanned OK [%s]: %d", ext, len(paths_ext))
                for p in paths_ext:
                    logger.info("  %s", p)

    # Group duplicates based on pHash
    groups, duplicate_map = _group_duplicates(results, threshold=config.duplicate_threshold)
    duplicate_groups = sum(1 for g in groups if len(g.members) > 1)

    # Plan moves
    plans: List[MovePlan] = []
    blurred_count = 0
    partial_blurred_count = 0
    slightly_blurred_count = 0
    duplicates_count = 0

    for r in results:
        if r.error:
            continue
        is_dup = duplicate_map.get(r.path, False)
        reason: Optional[str] = None

        # Blur classification
        blur_reason: Optional[str] = None
        if config.blur_on == "image":
            is_blur = (r.blur_variance is not None) and (r.blur_variance < config.blur_threshold)
            if is_blur:
                blur_reason = "blurred"
        else:  # faces
            face_vars = r.faces_variances or []
            face_count = len(face_vars)
            if face_count > 0:
                blurred_faces = sum(1 for v in face_vars if v < config.blur_threshold)
                if blurred_faces == face_count:
                    blur_reason = "blurred"
                else:
                    percent = (blurred_faces / face_count) * 100.0
                    if percent >= config.partial_blur_min_percent:
                        blur_reason = "partialBlurred"
                    elif blurred_faces > 0:
                        blur_reason = "slightlyBlurred"
            else:
                # No faces detected; fall back to image-level blur classification
                if (r.blur_variance is not None) and (r.blur_variance < config.blur_threshold):
                    blur_reason = "blurred"
                    logger.debug(
                        "No faces in %s; falling back to image blur: var=%.2f<thr=%.2f",
                        r.path,
                        r.blur_variance if r.blur_variance is not None else float("nan"),
                        config.blur_threshold,
                    )

        # Combine with duplicate precedence
        if is_dup and blur_reason:
            reason = "duplicate" if config.prefer_duplicate_over_blur else blur_reason
        elif is_dup:
            reason = "duplicate"
        elif blur_reason:
            reason = blur_reason
        if not reason:
            continue
        if reason == "duplicate":
            dest_dir = dup_dir
        elif reason == "blurred":
            dest_dir = blur_dir
        elif reason == "partialBlurred":
            dest_dir = partial_blur_dir
        else:  # slightlyBlurred
            dest_dir = slight_blur_dir
        dest = dest_dir / r.path.name
        plans.append(MovePlan(src=r.path, dest=dest, reason=reason))

    # Optional: print per-file metrics (blur variance and face count) with final reason
    if config.print_metrics:
        if config.print_format == "csv":
            logger.info("ext,path,blur_var,faces,reason")
            reason_by_src = {pl.src: pl.reason for pl in plans}
            for r in results:
                if r.error:
                    continue
                ext = r.path.suffix.lower()
                faces = len(r.faces_variances or [])
                reason = reason_by_src.get(r.path, "")
                logger.info("%s,%s,%.6f,%d,%s", ext, r.path, (r.blur_variance or float("nan")), faces, reason)
        else:
            logger.info("Per-file metrics (variance of Laplacian; faces; reason):")
            reason_by_src = {pl.src: pl.reason for pl in plans}
            for r in results:
                if r.error:
                    continue
                faces = len(r.faces_variances or [])
                reason = reason_by_src.get(r.path, "-")
                logger.info("  %s  var=%.2f  faces=%d  reason=%s", r.path, (r.blur_variance or float("nan")), faces, reason)

    # Execute plans
    if not config.dry_run:
        # Create target folders up front
        ensure_dir(blur_dir)
        ensure_dir(partial_blur_dir)
        ensure_dir(slight_blur_dir)
        ensure_dir(dup_dir)

    # Optional: print plans grouped by extension before executing
    if config.print_ready:
        by_ext: Dict[str, List[MovePlan]] = {}
        for pl in plans:
            ext = pl.src.suffix.lower()
            by_ext.setdefault(ext, []).append(pl)
        if config.print_format == "csv":
            logger.info("ext,reason,src,dest")
            for ext, pls in sorted(by_ext.items()):
                for pl in pls:
                    logger.info("%s,%s,%s,%s", ext, pl.reason, pl.src, pl.dest)
        else:
            for ext, pls in sorted(by_ext.items()):
                logger.info("Ready to move [%s]: %d", ext, len(pls))
                for pl in pls:
                    logger.info("  %-9s: %s -> %s", pl.reason, pl.src, pl.dest)

    for plan in tqdm(plans, total=len(plans), desc=("Copying" if config.keep_originals else "Moving"), unit="file"):
        if config.dry_run:
            logger.info("[DRY-RUN] %-9s: %s -> %s", plan.reason, plan.src, plan.dest)
        else:
            try:
                moved_path = move_or_copy(plan, copy=config.keep_originals)
                if plan.reason == "duplicate":
                    duplicates_count += 1
                elif plan.reason == "blurred":
                    blurred_count += 1
                elif plan.reason == "partialBlurred":
                    partial_blurred_count += 1
                elif plan.reason == "slightlyBlurred":
                    slightly_blurred_count += 1
                logger.debug("%s -> %s", plan.src, moved_path)
            except Exception as e:
                error_count += 1
                logger.warning("Failed to %s %s -> %s: %s", "copy" if config.keep_originals else "move", plan.src, plan.dest, e)

    # Summary
    if config.dry_run:
        # Count from plans
        blurred_count = sum(1 for p in plans if p.reason == "blurred")
        partial_blurred_count = sum(1 for p in plans if p.reason == "partialBlurred")
        slightly_blurred_count = sum(1 for p in plans if p.reason == "slightlyBlurred")
        duplicates_count = sum(1 for p in plans if p.reason == "duplicate")

    logger.info(
        "Summary: scanned=%d, blurred=%d, partial=%d, slight=%d, duplicates=%d (groups=%d), errors=%d",
        total,
        blurred_count,
        partial_blurred_count,
        slightly_blurred_count,
        duplicates_count,
        duplicate_groups,
        error_count,
    )

    return 0
