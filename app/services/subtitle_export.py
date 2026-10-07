"""Convert a task's generated SRT subtitle into other free formats."""

from __future__ import annotations

import re

SUPPORTED_FORMATS = ("srt", "vtt")

_SRT_TIMESTAMP = re.compile(r"(\d{1,2}:\d{2}:\d{2}),(\d{3})")


def srt_to_vtt(srt_text: str) -> str:
    """Return WebVTT for ``srt_text``.

    WebVTT differs from SRT in three ways that matter here: a ``WEBVTT`` header,
    ``.`` instead of ``,`` before the milliseconds, and no BOM. Cue numbers are
    valid WebVTT cue identifiers, so they are kept.
    """
    text = srt_text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    for line in text.split("\n"):
        if "-->" in line:
            line = _SRT_TIMESTAMP.sub(r"\1.\2", line)
        lines.append(line)
    body = "\n".join(lines).strip("\n")
    return f"WEBVTT\n\n{body}\n" if body else "WEBVTT\n"


def convert(srt_text: str, fmt: str) -> tuple[str, str]:
    """Return ``(content, media_type)`` for a supported ``fmt``."""
    fmt = fmt.lower()
    if fmt == "srt":
        normalized = srt_text.lstrip("\ufeff").replace("\r\n", "\n")
        return normalized, "application/x-subrip"
    if fmt == "vtt":
        return srt_to_vtt(srt_text), "text/vtt"
    raise ValueError(f"unsupported subtitle format: {fmt}")
