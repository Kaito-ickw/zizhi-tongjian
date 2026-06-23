#!/usr/bin/env python3
"""Resize and recompress an image into the generated documentation tree."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MAX_BYTES = 300 * 1024
QUALITY_RANGE = range(4, 13)
YEAR_RE = re.compile(r"y\d{2}")
SLUG_RE = re.compile(r"[A-Za-z0-9_-]+")
DIMENSIONS_RE = re.compile(r"\bs:(\d+)x(\d+)\b")
SCALE_FILTER = (
    r"scale=min(1600\,iw):min(1600\,ih):"
    "force_original_aspect_ratio=decrease:force_divisible_by=2,showinfo"
)


class ImageSyncError(Exception):
    """A user-facing image synchronization error."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compress and place an illustration in docs/images/."
    )
    parser.add_argument("src", type=Path)
    parser.add_argument("juan", type=int)
    parser.add_argument("year", help="year identifier such as y01")
    parser.add_argument("slug")
    return parser.parse_args()


def sync_image(
    src: Path, juan: int, year: str, slug: str
) -> tuple[Path, int, int, int]:
    if not src.is_file():
        raise ImageSyncError(f"source image does not exist: {src}")
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise ImageSyncError("ffmpeg was not found in PATH")
    if juan < 1:
        raise ImageSyncError("juan must be a positive integer")
    if YEAR_RE.fullmatch(year) is None:
        raise ImageSyncError("year must match yNN (for example, y01)")
    if SLUG_RE.fullmatch(slug) is None:
        raise ImageSyncError("slug may contain only letters, digits, '_' and '-'")

    destination_dir = ROOT / "docs" / "images" / f"卷{juan:03d}"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"j{juan:03d}_{year}_{slug}.jpg"

    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{destination.stem}.",
            suffix=".jpg",
            dir=destination_dir,
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
        temporary_path = Path(temporary_name)

        dimensions: tuple[int, int] | None = None
        for quality in QUALITY_RANGE:
            command = [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "info",
                "-y",
                "-i",
                str(src),
                "-map_metadata",
                "-1",
                "-vf",
                SCALE_FILTER,
                "-frames:v",
                "1",
                "-q:v",
                str(quality),
                str(temporary_path),
            ]
            result = subprocess.run(command, capture_output=True, text=True)
            if result.returncode != 0:
                detail = result.stderr.strip().splitlines()
                message = detail[-1] if detail else "unknown ffmpeg error"
                raise ImageSyncError(f"ffmpeg failed: {message}")

            matches = DIMENSIONS_RE.findall(result.stderr)
            if not matches:
                raise ImageSyncError("ffmpeg did not report the output dimensions")
            dimensions = tuple(map(int, matches[-1]))
            if temporary_path.stat().st_size <= MAX_BYTES:
                break

        if dimensions is None:
            raise ImageSyncError("ffmpeg did not produce an image")
        size = temporary_path.stat().st_size
        temporary_path.replace(destination)
        temporary_name = None
        return destination, dimensions[0], dimensions[1], size
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def main() -> int:
    args = parse_args()
    try:
        destination, width, height, size = sync_image(
            args.src, args.juan, args.year, args.slug
        )
    except ImageSyncError as exc:
        print(f"image_sync.py: error: {exc}", file=sys.stderr)
        return 1

    print(f"{destination.relative_to(ROOT)}: {width}x{height}, {size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
