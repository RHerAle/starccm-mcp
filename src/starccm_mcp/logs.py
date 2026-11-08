# starccm-mcp
# © 2026 RHerAle
# SPDX-License-Identifier: GPL-3.0-only
# Additional terms under section 7 of the GPL apply: see NOTICE.
"""Reads STAR-CCM+ output logs: the iteration table, solver events and the tail of the text.

Works on any text that contains the solver output: messages.log of the desktop client, the output of a
batch run, or a log saved from the Output window. Everything returned goes through masking.mask().
"""
from __future__ import annotations

import re
from pathlib import Path

from .masking import mask

_HEADER = re.compile(r"^\s*Iteration\s{2,}\S")
_DIGITS = re.compile(r"[-+]?\d[\d.eE+-]*")
_NUM = re.compile(r"^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$|^-?(nan|inf)", re.I)
_EVENTS = [
    ("amg", re.compile(r"(?i)AMG solve(r)? (diverged|rejected)")),
    ("error", re.compile(r"^\s*Error\b|\bERROR\b|^\s*(Caused:\s*)?[\w.$]*(Exception|Error)\b:")),
    ("reversed_flow", re.compile(r"(?i)Reversed flow on")),
    ("limited", re.compile(r"(?i)\blimited\b.*\bon \d+ cells")),
    ("floating_point", re.compile(r"(?i)floating point exception")),
    ("stopping", re.compile(r"(?i)stopping criteri|criterion.*satisfied|\bStop(ping)? file\b")),
    ("warning", re.compile(r"(?i)\bwarning\b")),
    ("save", re.compile(r"(?i)\bSav(ing|ed) Simulation\b|\bSaving:")),
]


def read_text(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8", errors="replace")


def tail(text: str, lines: int = 200, grep: str | None = None) -> str:
    rows = text.splitlines()
    if grep:
        pat = re.compile(grep, re.I)
        rows = [r for r in rows if pat.search(r)]
    return mask("\n".join(rows[-lines:]))


def _row(tokens: list[str], ncols: int) -> list[float] | None:
    if len(tokens) != ncols or not tokens[0].isdigit() or not all(_NUM.match(t) for t in tokens[1:]):
        return None
    try:
        return [float(t) for t in tokens]
    except ValueError:
        return None


def summarize(text: str, last_rows: int = 10) -> dict:
    """Iteration table (columns, first and last rows), grouped solver events and the last lines of text."""
    columns: list[str] = []
    rows: list[list[float]] = []
    tables = 0
    events: dict[str, dict] = {}
    other: list[str] = []
    iteration = None
    for line in text.splitlines():
        if _HEADER.match(line):
            tables += 1
            names = re.split(r"\s{2,}", line.strip())
            if names != columns:
                columns = names
            continue
        tokens = line.split()
        r = _row(tokens, len(columns)) if columns else None
        if r is not None:
            iteration = int(r[0])
            rows.append(r)
            continue
        s = line.strip()
        if not s:
            continue
        other.append(s)
        for kind, pat in _EVENTS:
            if pat.search(s):
                key = kind + ": " + _DIGITS.sub("#", s)[:120]
                e = events.setdefault(key, {"kind": kind, "count": 0, "first_iteration": iteration,
                                            "last_iteration": iteration, "example": mask(s[:200])})
                e["count"] += 1
                e["last_iteration"] = iteration
                break
    fmt = lambda r: dict(zip(columns, [int(r[0])] + r[1:]))
    return {
        "columns": columns,
        "tables_printed": tables,
        "rows": len(rows),
        "first_row": fmt(rows[0]) if rows else None,
        "last_rows": [fmt(r) for r in rows[-last_rows:]],
        "events": sorted(events.values(), key=lambda e: -e["count"])[:40],
        "last_lines": [mask(s[:200]) for s in other[-15:]],
    }
