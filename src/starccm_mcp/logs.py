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
_NUM = re.compile(r"^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$")
# Non-finite values as C runtimes print them when a run diverges: nan, -nan(ind), 1.#QNAN, inf, 1.#INF...
_NONFINITE = re.compile(r"^[-+]?(nan(\(\w*\))?|inf(inity)?|1\.#(QNAN|SNAN|IND|INF)\d*)$", re.I)
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
    rows = mask(text).splitlines()  # mask first, so grep cannot probe for hidden values
    if grep:
        pat = re.compile(grep, re.I)
        rows = [r for r in rows if pat.search(r)]
    return "\n".join(rows[-lines:])


def _value(t: str) -> float | str | None:
    if _NUM.match(t):
        return float(t)
    if _NONFINITE.match(t):
        return t  # kept as printed: JSON has no NaN, and the text says how the run failed
    return None


def _row(tokens: list[str], columns: list[str]) -> dict | None:
    if len(tokens) != len(columns) or not tokens[0].isdigit():
        return None
    values = [_value(t) for t in tokens[1:]]
    if any(v is None for v in values):
        return None
    return dict(zip(columns, [int(tokens[0])] + values))


def summarize(text: str, last_rows: int = 10) -> dict:
    """Iteration table (columns, first and last rows), grouped solver events and the last lines of text.

    Each row is labelled with the header printed above it, so tables whose columns change stay correct.
    """
    text = mask(text)  # mask first: nothing below can return an unmasked fragment
    columns: list[str] = []
    rows: list[dict] = []
    tables = 0
    events: dict[str, dict] = {}
    other: list[str] = []
    iteration = None
    for line in text.splitlines():
        if _HEADER.match(line):
            tables += 1
            columns = re.split(r"\s{2,}", line.strip())
            continue
        r = _row(line.split(), columns) if columns else None
        if r is not None:
            iteration = r[columns[0]]
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
                                            "last_iteration": iteration, "example": s[:200]})
                e["count"] += 1
                e["last_iteration"] = iteration
                break
    return {
        "columns": columns,
        "tables_printed": tables,
        "rows": len(rows),
        "first_row": rows[0] if rows else None,
        "last_rows": rows[-last_rows:],
        "events": sorted(events.values(), key=lambda e: -e["count"])[:40],
        "last_lines": [s[:200] for s in other[-15:]],
    }
