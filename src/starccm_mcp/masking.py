# starccm-mcp
# © 2026 RHerAle
# SPDX-License-Identifier: GPL-3.0-only
# Additional terms under section 7 of the GPL apply: see NOTICE.
"""Removes licence data from any text before it leaves the server.

STAR-CCM+ puts the Power-on-Demand key and the licence server on the command line of every server
process, and the logs can repeat them. Nothing this server returns should contain them. Mask whole texts
before filtering or truncating them, never after.
"""
from __future__ import annotations

import re

_RULES = [
    # -podkey KEY, -licpath 1999@host, -licserver ..., -lic ..., also with = or :
    (re.compile(r"(?i)(-{1,2}D?(?:podkey|pod_key|licpath|licserver|lic)\b)(\s*[=:]\s*|\s+)(\"[^\"]*\"|\S+)"),
     r"\1\2<masked>"),
    # podkey: KEY, POD_KEY=KEY, "podkey": "KEY", CDLMD_LICENSE_FILE=..., License server: host
    (re.compile(r"(?i)(\b\w*(?:pod_?key|licen[sc]e[\w ]{0,20}?|lic_?path|lic_?server)\"?\s*[=:]\s*)(\"[^\"]*\"|\S+)"),
     r"\1<masked>"),
    # port@host licence addresses
    (re.compile(r"\b\d{2,5}@[A-Za-z0-9][\w.\-]*"), "<masked>"),
    # IPv4 addresses
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"), "<masked-ip>"),
]
# Opaque tokens (keys, hashes): 20+ characters of [A-Za-z0-9+/], with letters and digits. Underscores, dots and
# hyphens break a token, so names such as 20241217_1200_AAPL3_wing_M141 survive.
_TOKEN = re.compile(r"(?<![\w\\/.\-])[A-Za-z0-9+/]{20,}={0,2}(?![\w\-])")


def _token(m: re.Match) -> str:
    s = m.group(0)
    return "<masked-token>" if any(c.isdigit() for c in s) and any(c.isalpha() for c in s) else s


def mask(text: str) -> str:
    for pattern, repl in _RULES:
        text = pattern.sub(repl, text)
    return _TOKEN.sub(_token, text)
