"""Removes licence data from any text before it leaves the server.

STAR-CCM+ puts the Power-on-Demand key and the licence server on the command line of every server
process, and the logs can repeat them. Nothing this server returns should contain them.
"""
from __future__ import annotations

import re

_RULES = [
    # -podkey KEY, -licpath 1999@host, -licserver ..., -lic ...
    (re.compile(r"(?i)(-podkey|-licpath|-licserver|-lic\b)(\s+|=)(\"[^\"]*\"|\S+)"), r"\1\2<masked>"),
    # CDLMD_LICENSE_FILE=..., LM_LICENSE_FILE=..., SIEMENS_LICENSE_FILE=...
    (re.compile(r"(?i)\b(\w*licen[sc]e\w*)\s*=\s*(\"[^\"]*\"|\S+)"), r"\1=<masked>"),
    # port@host licence addresses
    (re.compile(r"\b\d{2,5}@[A-Za-z0-9][\w.\-]*"), "<masked>"),
    # IPv4 addresses
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"), "<masked-ip>"),
    # long opaque tokens with letters and digits (keys, hashes)
    (re.compile(r"(?<![\w\\/.])(?=[A-Za-z0-9+/_-]*\d)(?=[A-Za-z0-9+/_-]*[A-Za-z])[A-Za-z0-9+/_-]{20,}={0,2}"),
     "<masked-token>"),
]


def mask(text: str) -> str:
    for pattern, repl in _RULES:
        text = pattern.sub(repl, text)
    return text
