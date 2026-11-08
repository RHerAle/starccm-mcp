# starccm-mcp
# © 2026 RHerAle
# SPDX-License-Identifier: GPL-3.0-only
# Additional terms under section 7 of the GPL apply: see NOTICE.
"""Finds the STAR-CCM+ installation, its documentation, the per-user log and a cache folder."""
from __future__ import annotations

import glob
import os
from pathlib import Path

INSTALL_PATTERNS = (
    r"C:\Program Files\Siemens\*\STAR-CCM+*",
    "/opt/Siemens/*/STAR-CCM+*",
    "/opt/Siemens/STAR-CCM+*",
)


class NotFound(RuntimeError):
    """A file or folder the tool needs does not exist; the message says how to fix it."""


def install_dir() -> Path:
    """Folder that contains star/ and doc/. STARCCM_HOME wins; otherwise the newest default install."""
    env = os.environ.get("STARCCM_HOME")
    if env:
        p = Path(env)
        if (p / "star").is_dir():
            return p
        raise NotFound(f"STARCCM_HOME={env} has no 'star' folder. Point it at the folder that holds star/ and doc/.")
    found = sorted({Path(p) for pat in INSTALL_PATTERNS for p in glob.glob(pat) if (Path(p) / "star").is_dir()},
                   key=lambda p: p.name)
    if not found:
        raise NotFound("No STAR-CCM+ installation found. Set STARCCM_HOME to the folder that holds star/ and doc/, "
                       r"e.g. C:\Program Files\Siemens\20.02.008-R8\STAR-CCM+20.02.008-R8")
    return found[-1]


def batch_launcher() -> Path:
    exe = install_dir() / "star" / "bin" / ("starccm+.bat" if os.name == "nt" else "starccm+")
    if not exe.exists():
        raise NotFound(f"Launcher not found: {exe}")
    return exe


def manual_dir() -> Path:
    pages = sorted((install_dir() / "doc").glob("*/online/STARCCMP"), key=lambda p: p.parent.parent.name != "en")
    if not pages:
        raise NotFound("The HTML user guide (doc/<lang>/online/STARCCMP) is not installed.")
    return pages[0]


def javadoc_dir() -> Path:
    d = install_dir() / "doc" / "client" / "html"
    if not (d / "star").is_dir():
        raise NotFound(f"The Java API reference is not installed in {d}.")
    return d


def default_log() -> Path:
    """Newest messages.log of the desktop client (Windows layout: %LOCALAPPDATA%/Siemens/STAR-CCM+ <ver>/var/log)."""
    base = os.environ.get("LOCALAPPDATA")
    found = glob.glob(os.path.join(base, "Siemens", "STAR-CCM+ *", "var", "log", "messages.log")) if base else []
    if not found:
        raise NotFound("No messages.log found. Pass the path of a STAR-CCM+ output log explicitly.")
    return max((Path(p) for p in found), key=lambda p: p.stat().st_mtime)


def cache_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".cache")
    d = Path(base) / "starccm-mcp"
    d.mkdir(parents=True, exist_ok=True)
    return d
