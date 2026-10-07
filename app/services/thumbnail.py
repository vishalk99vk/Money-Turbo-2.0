"""Free, local cover-thumbnail generation for finished videos.

Samples a handful of frames, scores each one for detail (edge energy) and
brightness, and saves the best as a JPEG. Pure local compute: no API keys.

Usage:
    python -m app.services.thumbnail path/to/video.mp4 [out.jpg]
"""

from __future__ import annotations

import hashlib
import os
import sys

from loguru import logger
from PIL import Image, ImageFilter, ImageStat

from app.utils import utils

# Candidate positions as a fraction of the video length. The very first and last
# frames are skipped because they are often black or a fade.
CANDIDATE_POSITIONS = (0.1, 0.25, 0.4, 0.55, 0.7, 0.85)
MAX_WIDTH = 1280
JPEG_QUALITY = 88


def score_frame(image: Image.Image) -> float:
    """Higher is better: detailed (edge variance) and neither black nor blown out."""
    gray = image.convert("L")
    small = gray.copy()
    small.thumbnail((320, 320))
    edge_variance = ImageStat.Stat(small.filter(ImageFilter.FIND_EDGES)).var[0]
    brightness = ImageStat.Stat(small).mean[0]
    # 1.0 at mid-grey, falling to 0 at pure black / pure white.
    exposure = max(0.0, 1.0 - abs(brightness - 128.0) / 128.0)
    return edge_variance * (0.25 + 0.75 * exposure)


def pick_best_frame(frames: list[Image.Image]) -> Image.Image:
    if not frames:
        raise ValueError("no frames to choose from")
    return max(frames, key=score_frame)


def _sample_frames(video_path: str) -> list[Image.Image]:
    from moviepy import VideoFileClip

    frames: list[Image.Image] = []
    with VideoFileClip(video_path) as clip:
        duration = float(clip.duration or 0)
        times = [duration * p for p in CANDIDATE_POSITIONS] if duration > 0 else [0.0]
        for t in times:
            try:
                frames.append(Image.fromarray(clip.get_frame(min(t, max(duration - 0.05, 0)))))
            except Exception as exc:  # a bad frame must not kill the whole job
                logger.warning(f"thumbnail: skipping frame at {t:.2f}s ({type(exc).__name__})")
    return frames


def generate_thumbnail(video_path: str, output_path: str) -> str:
    """Write the best frame of ``video_path`` to ``output_path`` and return it."""
    frames = _sample_frames(video_path)
    if not frames:
        raise RuntimeError("could not read any frame from the video")
    best = pick_best_frame(frames).convert("RGB")
    if best.width > MAX_WIDTH:
        ratio = MAX_WIDTH / best.width
        best = best.resize((MAX_WIDTH, max(1, round(best.height * ratio))), Image.LANCZOS)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    tmp_path = f"{output_path}.tmp"
    best.save(tmp_path, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    os.replace(tmp_path, output_path)  # atomic publish: readers never see half a file
    return output_path


def cached_thumbnail_path(video_path: str) -> str:
    """Cache key covers path, size and mtime so a re-rendered video refreshes it."""
    stat = os.stat(video_path)
    key = f"{os.path.realpath(video_path)}|{stat.st_size}|{stat.st_mtime_ns}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
    return os.path.join(utils.storage_dir("thumbnails", create=True), f"{digest}.jpg")


def get_or_create_thumbnail(video_path: str) -> str:
    target = cached_thumbnail_path(video_path)
    if os.path.isfile(target) and os.path.getsize(target) > 0:
        return target
    return generate_thumbnail(video_path, target)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: python -m app.services.thumbnail VIDEO [OUT.jpg]")
    source = sys.argv[1]
    result = (
        generate_thumbnail(source, sys.argv[2])
        if len(sys.argv) > 2
        else get_or_create_thumbnail(source)
    )
    print(result)
