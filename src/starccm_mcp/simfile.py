# starccm-mcp
# © 2026 RHerAle
# SPDX-License-Identifier: GPL-3.0-only
# Additional terms under section 7 of the GPL apply: see NOTICE.
"""Reads the object state stored in a STAR-CCM+ .sim file, without STAR-CCM+ and without a licence.

The format is not documented by Siemens. What follows was observed on files saved by STAR-CCM+ 2502 (20.02):

- The first line is a dict with 'ClassName': 'STAR' and 'StatePosition': N.
- From byte N to the end of the file, each line is one object, written as a Python-like dict.
  Object number r sits on line r + 2 of that block.
- Integers with an L suffix are usually references to other objects, but not always
  ('FaceCount', 'dataKey' and similar are plain numbers).
- Arrays such as 'MasterArray<Float8>' (monitor histories) keep their data elsewhere in the file:
  'dataKey' is an absolute byte offset to a one-line header followed by little-endian doubles.

The file is only ever opened for reading.
"""
from __future__ import annotations

import ast
import os
import re
import struct
import threading
from collections import OrderedDict
from typing import Any

_LNUM = re.compile(r"(?<![\w.])(-?\d+)L\b")
_LITERALS = [(re.compile(r"(?<=[\s\[:,])" + w + r"(?=[\s,\]}])"), py)
             for w, py in (("true", "True"), ("false", "False"), ("null", "None"))]
_NOISE = {"Parent", "NameManager", "Manager", "ClientServerObjectGroupManager", "ObjectId", "ChildManager", "Index",
          "FunctionExpression", "DimensionsVector", "ExecuteTimeStamp", "TimeStamp", "GlobalData", "MetaData",
          "AssemblyCode", "ClassName", "PresentationName", "StagedObjectMap", "StageMap", "ExpressionMap"}
_WRAPPER_SUFFIXES = ("Quantity", "Value", "Method", "Profile")


_PLAIN_INT_KEYS = {"dataKey", "size", "nElements", "PlotLimit", "SampledIteration", "SampledTimeLevel", "StartIteration",
                   "CurrentIteration", "CurrentTimeLevel", "HeadingPrintFrequency", "MaxPrintOrder", "NumberOfSteps",
                   "Verbosity", "TimeDataOffset", "SatisfiedIteration"}


def _plain_int(key: str) -> bool:
    """Fields whose integers are counts or offsets, not references."""
    return key in _PLAIN_INT_KEYS or key.endswith("Count")


def short(cls: Any) -> str:
    return str(cls).rsplit(".", 1)[-1]


def _parse(line: bytes) -> dict | None:
    s = line.decode("utf-8", "replace").strip()
    if not s.startswith("{"):
        return None
    s2 = _LNUM.sub(r"\1", s)
    for pattern, py in _LITERALS:
        s2 = pattern.sub(py, s2)
    try:
        d = ast.literal_eval(s2)
    except (ValueError, SyntaxError, MemoryError, RecursionError):
        return {"_raw": s[:2000]}
    return d if isinstance(d, dict) else None


class SimFile:
    def __init__(self, path: str):
        self.path = os.path.abspath(path)
        self.size = os.path.getsize(self.path)
        with open(self.path, "rb") as f:
            head = f.readline(4096).decode("latin-1")
            m = re.search(r"'StatePosition':\s*(\d+)", head)
            if "'ClassName': 'STAR'" not in head or not m:
                raise ValueError(f"{path} does not look like a STAR-CCM+ .sim file (no STAR header with StatePosition).")
            f.seek(int(m.group(1)))
            blob = f.read()
        self.records = [_parse(line) for line in blob.split(b"\n")]
        self.by_class: dict[str, list[int]] = {}
        for i, d in enumerate(self.records):
            if d and "ClassName" in d:
                self.by_class.setdefault(short(d["ClassName"]), []).append(i - 2)

    # ---- basic access -------------------------------------------------------------------------
    def is_ref(self, v: Any) -> bool:
        """True if v can be a reference: a positive int that points at a parsed record (0 means 'none')."""
        return isinstance(v, int) and not isinstance(v, bool) and 0 < v < len(self.records) - 2 and bool(self.records[v + 2])

    def rec(self, r: Any) -> dict:
        return self.records[r + 2] if self.is_ref(r) else {}

    def raw(self, r: int) -> dict:
        """Record by number without the reference check (the version records sit at -2 and 0)."""
        return self.records[r + 2] or {} if -2 <= r < len(self.records) - 2 else {}

    def ids(self, *classes: str) -> list[int]:
        return sorted(r for c in classes for r in self.by_class.get(c, []))

    def cls(self, r: Any) -> str:
        return short(self.rec(r).get("ClassName", ""))

    def name(self, r: Any) -> str:
        d = self.rec(r)
        return d.get("PresentationName") or short(d.get("ClassName", ""))

    def first(self, cls: str) -> dict:
        ids = self.ids(cls)
        return self.rec(ids[0]) if ids else {}

    def keys_of(self, r: Any) -> list[int]:
        return [k for k in self.rec(r).get("Keys", []) if self.is_ref(k)]

    def units(self, d: dict) -> str:
        return self.rec(d.get("Units")).get("PresentationName", "") if self.is_ref(d.get("Units")) else ""

    # ---- values -------------------------------------------------------------------------------
    def quantity(self, r: Any, depth: int = 0) -> dict | None:
        """Active value of a setting: follows Method -> Quantity -> value and returns value, units, definition."""
        d = self.rec(r)
        if not d or depth > 5:
            return None
        has_value = "Value" in d or "Vector" in d
        if has_value and ("Units" in d or "Definition" in d or "DimensionsVector" in d):
            out: dict[str, Any] = {"value": d["Value"] if "Value" in d else d["Vector"], "units": self.units(d)}
            if d.get("Definition"):
                out["definition"] = d["Definition"]
            return out
        for key in ("Method", "Quantity", "Value"):
            v = d.get(key)
            if self.is_ref(v) and self.cls(v).endswith(_WRAPPER_SUFFIXES):
                q = self.quantity(v, depth + 1)
                if q is not None:
                    return {"method": self.cls(v), **q} if key == "Method" else q
        return None

    def settings(self, r: Any, depth: int = 1, _seen: set | None = None) -> dict:
        """The object's own fields, with references resolved to names, values or (to `depth`) nested objects."""
        seen = _seen if _seen is not None else set()
        seen.add(r)
        d = self.rec(r)
        out: dict[str, Any] = {}
        for k, v in d.items():
            if k in _NOISE:
                continue
            if isinstance(v, list):
                refs = [x for x in v if self.is_ref(x)]
                if refs and len(refs) == len(v):
                    out[k] = [self._ref_summary(x, depth, seen) for x in refs[:50]]
                elif len(str(v)) < 300:
                    out[k] = v
            elif self.is_ref(v) and not _plain_int(k):
                out[k] = self._ref_summary(v, depth, seen)
            elif not isinstance(v, (dict, list)):
                out[k] = v
        return out

    def _ref_summary(self, x: int, depth: int, seen: set) -> Any:
        t = self.rec(x)
        q = self.quantity(x)
        if q is not None:
            return q
        if "Selected" in t:
            return {"option": self.cls(x), "selected_index": t["Selected"]}
        label = f"{t.get('PresentationName', '')} [{self.cls(x)} #{x}]".strip()
        if depth > 0 and x not in seen:
            nested = self.settings(x, depth - 1, seen)
            return {"object": label, **nested} if nested else label
        return label

    def array(self, r: Any) -> list[float]:
        d = self.rec(r)
        if not str(d.get("ClassName", "")).startswith("MasterArray<Float8>"):
            raise ValueError(f"record {r} is not a MasterArray<Float8>")
        key, n = d.get("dataKey", 0), d.get("size", 0)
        if not key or not n:
            return []
        with open(self.path, "rb") as f:
            f.seek(key)
            head = f.readline(512).decode("latin-1")
            if "'Float8'" not in head:
                raise ValueError(f"unexpected array header at byte {key}: {head[:120]!r}")
            m = re.search(r"'nElements':\s*(\d+)", head)
            count = int(m.group(1)) if m else n
            data = f.read(8 * count)
        return list(struct.unpack(f"<{len(data) // 8}d", data[: 8 * (len(data) // 8)]))


# ---- cache ----------------------------------------------------------------------------------------
_CACHE: "OrderedDict[tuple, SimFile]" = OrderedDict()
_LOCK = threading.Lock()


def open_sim(path: str) -> SimFile:
    p = os.path.abspath(os.path.expanduser(path))
    if not os.path.isfile(p):
        raise FileNotFoundError(f"No such file: {p}")
    st = os.stat(p)
    key = (p, st.st_mtime_ns, st.st_size)
    with _LOCK:
        if key in _CACHE:
            _CACHE.move_to_end(key)
            return _CACHE[key]
    sim = SimFile(p)
    with _LOCK:
        _CACHE[key] = sim
        while len(_CACHE) > 3:
            _CACHE.popitem(last=False)
    return sim


# ---- views ----------------------------------------------------------------------------------------
def overview(sim: SimFile, history: int = 5) -> dict:
    ver = sim.raw(sim.ids("StarVersion")[-1]) if sim.ids("StarVersion") else {}
    s = sim.first("Simulation")
    it = sim.first("SimulationIterator")
    mesh = next((sim.rec(r) for r in sim.ids("FvRepresentation") if sim.rec(r).get("CellCount") is not None), {})
    log = sim.first("StarLog").get("Log", "")
    entries = [e.strip() for e in re.split(r"-{20,}", log) if e.strip()]
    criteria = []
    for r in sim.ids(*[c for c in sim.by_class if c.endswith("StoppingCriterion")]):
        d = sim.rec(r)
        criteria.append({"name": d.get("PresentationName"), "class": sim.cls(r), "used": d.get("IsUsed"),
                         "satisfied": d.get("IsSatisfied"),
                         "settings": {k: v for k, v in sim.settings(r, 1).items()
                                      if k not in ("IsUsed", "IsSatisfied", "LogicalOperationOption")}})
    continua = []
    for r in sim.ids("PhysicsContinuum", "MeshContinuum"):
        d = sim.rec(r)
        continua.append({"name": d.get("PresentationName"), "models": [sim.cls(m) for m in sim.keys_of(d.get("ModelManager"))]})
    mon_mgr = sim.ids("MonitorManager")
    rep_mgr = sim.ids("ReportManager")
    mop_mgr = sim.ids("MeshOperationManager")
    return {
        "file": sim.path,
        "size_mb": round(sim.size / 2**20, 2),
        "simulation": s.get("name"),
        "saved_with": f"{ver.get('PresentationVersion', '?')} ({ver.get('ReleaseNumber', '?')})",
        "parallel": s.get("parallel"),
        "current_iteration": it.get("CurrentIteration"),
        "elapsed_time_s": it.get("ElapsedTime"),
        "volume_mesh": {"cells": mesh.get("CellCount"), "interior_faces": mesh.get("InteriorFaceCount"),
                        "vertices": mesh.get("VertexCount")} if mesh else None,
        "regions": [sim.name(r) for r in sim.ids("Region")],
        "boundaries": len(sim.ids("Boundary")),
        "continua": continua,
        "parameters": [sim.name(r) for r in sim.ids("ScalarGlobalParameter", "VectorGlobalParameter")],
        "reports": [sim.name(r) for r in sim.keys_of(rep_mgr[0])] if rep_mgr else [],
        "monitors": [sim.name(r) for r in sim.keys_of(mon_mgr[0])] if mon_mgr else [],
        "mesh_operations": [f"{sim.name(r)} ({sim.cls(r)})" for r in sim.keys_of(mop_mgr[0])] if mop_mgr else [],
        "scenes": [sim.name(r) for r in sim.ids("Scene")],
        "stopping_criteria": criteria,
        "save_history": entries[-history:] if history else [],
        "records": len(sim.records),
    }


def parameters(sim: SimFile) -> list[dict]:
    out = []
    for r in sim.ids("ScalarGlobalParameter", "VectorGlobalParameter"):
        d = sim.rec(r)
        out.append({"name": d.get("PresentationName"), "type": sim.cls(r), **(sim.quantity(d.get("Quantity")) or {})})
    return out


def boundaries(sim: SimFile, region: str | None = None, name: str | None = None) -> list[dict]:
    out = []
    for r in sim.ids("Boundary"):
        d = sim.rec(r)
        reg = sim.name(d.get("Region"))
        if region and region.lower() != reg.lower() or name and name.lower() != str(d.get("PresentationName")).lower():
            continue
        stage = sim.rec(d.get("StageableConditionType"))
        options, values = {}, {}
        for mgr in sim.keys_of(d.get("Objects")):
            for k in sim.keys_of(mgr):
                o = sim.rec(k)
                key = sim.cls(k)
                if "Selected" in o:
                    options[key] = o["Selected"]
                else:
                    q = sim.quantity(k)
                    if q is not None:
                        values[key] = q
        out.append({"region": reg, "name": d.get("PresentationName"), "type": sim.cls(stage.get("BoundaryType")),
                    "record": r, "options_selected_index": options, "values": values})
    return out


def _monitor_ids(sim: SimFile) -> list[int]:
    mgr = sim.ids("MonitorManager")
    return [r for r in sim.keys_of(mgr[0]) if "XAxisData" in sim.rec(r)] if mgr else []


def monitors(sim: SimFile) -> list[dict]:
    out = []
    for r in _monitor_ids(sim):
        d = sim.rec(r)
        x = sim.rec(d.get("XAxisData"))
        out.append({"name": d.get("PresentationName"), "class": sim.cls(r),
                    "report": sim.name(d["Report"]) if sim.is_ref(d.get("Report")) else None,
                    "current_value": d.get("CurrentValue"), "stored_samples": x.get("size", 0)})
    return out


def monitor_series(sim: SimFile, name: str, last: int | None = 50, stride: int = 1) -> dict:
    match = [r for r in _monitor_ids(sim) if str(sim.rec(r).get("PresentationName")).lower() == name.lower()]
    if not match:
        raise KeyError(f"No monitor named {name!r}. Available: {[m['name'] for m in monitors(sim)]}")
    d = sim.rec(match[0])
    x = sim.array(d["XAxisData"])
    ys = sim.rec(d.get("MultiYAxisData"))
    series = {}
    for label, ref in zip(ys.get("keys", []), ys.get("values", [])):
        if sim.is_ref(ref) and sim.cls(ref).startswith("MasterArray<Float8>"):
            series[label] = sim.array(ref)
    n = len(x)
    lo = max(0, n - last) if last else 0
    sel = list(range(lo, n, max(1, stride)))
    if sel and sel[-1] != n - 1:
        sel.append(n - 1)
    return {"name": d.get("PresentationName"), "class": sim.cls(match[0]), "stored_samples": n,
            "x": [x[i] for i in sel], "y": {k: [v[i] for i in sel if i < len(v)] for k, v in series.items()}}


def find(sim: SimFile, pattern: str, where: str = "name", limit: int = 30, offset: int = 0) -> dict:
    pat = re.compile(pattern, re.I)
    hits = []
    for i, d in enumerate(sim.records):
        if not d or "ClassName" not in d:
            continue
        hay = {"name": str(d.get("PresentationName", "")), "class": short(d["ClassName"]), "text": str(d)}[where]
        if pat.search(hay):
            r = i - 2
            hits.append({"record": r, "class": short(d["ClassName"]), "name": d.get("PresentationName"),
                         "parent": sim.name(d.get("Parent")) if sim.is_ref(d.get("Parent")) else None})
    return {"total": len(hits), "offset": offset, "items": hits[offset: offset + limit],
            "has_more": len(hits) > offset + limit}
