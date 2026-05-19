"""Path-traversal guard for user-supplied media file paths.

Model providers accept image/audio paths originating from chat attachments,
Telegram uploads, browser screenshots, and ffmpeg frame extraction. Without
validation, a crafted path (e.g. ``../../etc/passwd`` or
``/etc/passwd``) would be opened and its contents base64-encoded into the
LLM request — a file-exfiltration primitive.

`validate_media_path` resolves the path with ``realpath`` (collapsing
symlinks and ``..``) and ensures it lands inside one of the directories
that legitimately hold user media.
"""

from __future__ import annotations

import os
from typing import Iterable

# Directories where user-supplied media legitimately lives:
#   /data/chat-uploads     dashboard chat attachments (+ extracted video frames)
#   /data/shared           Telegram-bridge downloads (+ extracted video frames at /data/shared/uploads/)
#   /data/screenshots      browser-skill captures (screenshot_<ts>.png)
#   /data/screenshot       legacy singular form, preserved for backwards compatibility
ALLOWED_MEDIA_DIRS: tuple[str, ...] = (
    "/data/chat-uploads",
    "/data/shared",
    "/data/screenshots",
    "/data/screenshot",
)


def validate_media_path(path: str | os.PathLike[str],
                        allowed: Iterable[str] | None = None) -> str:
    """Return the canonical realpath of *path* if it lives under an allowed
    media directory, otherwise raise ``ValueError``.

    The resolution uses ``os.path.realpath`` so that traversal sequences
    (``..``) and symlinks pointing outside the allowlist are rejected.

    Containment is checked against ``allowed_real + os.sep`` (not a bare
    prefix) so that ``/data/sharedfoo`` cannot impersonate ``/data/shared``.
    """
    if not path:
        raise ValueError("media path is empty")

    allow = tuple(allowed) if allowed is not None else ALLOWED_MEDIA_DIRS
    resolved = os.path.realpath(os.fspath(path))

    for base in allow:
        base_real = os.path.realpath(base)
        if resolved == base_real or resolved.startswith(base_real + os.sep):
            return resolved

    raise ValueError(
        f"media path resolves outside allowed directories: {os.fspath(path)!r}"
    )
