"""Finds running STAR-CCM+ servers and runs Java macros on them through a batch client.

A batch client started with `starccm+ -host localhost:<port> -batch Macro.java` connects to a server that is
already running, runs the macro and exits; the server and its GUI keep running. On the machine where this was
written the client did not ask for a licence (the server already holds one).

Safety rules, learnt the hard way: a read-only macro that called getters by reflection reached 3D-CAD sketch
objects on a parallel server whose CAD model was not loaded, and the server died with
"Non-recoverable ... isSerialCritical", taking the user's open simulation with it. Hence the checks below.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import tempfile
import uuid
from pathlib import Path

from . import paths
from .masking import mask

PORT_RANGE = range(47827, 48000)

# Never allowed: these either crashed a server or reach outside STAR-CCM+.
BLOCKED = [
    (r"\bjava\.lang\.reflect\b", "Java reflection (a reflective read-only macro crashed a parallel server)"),
    (r"\.(getDeclaredMethods?|getMethods?|getDeclaredFields?|getFields?)\s*\(", "reflective member lookup"),
    (r"\.invoke\s*\(", "reflective invoke"),
    (r"\.setAccessible\s*\(", "reflective access"),
    (r"\bClass\.forName\s*\(", "dynamic class loading"),
    (r"\bSystem\.exit\s*\(", "System.exit"),
    (r"\bRuntime\.getRuntime\s*\(\s*\)\s*\.\s*exec\b|\bProcessBuilder\b", "starting operating-system processes"),
]
# Allowed only with allow_risky=True, after the user has agreed.
RISKY = [
    (r"\bstar\.cadmodeler\b|\bCadModel\b|\bSketch\w*|getSketchPrimitiveManager",
     "3D-CAD access: on a parallel server whose CAD model is not loaded this can kill the server"),
    (r"\b(sim|simulation|getActiveSimulation\s*\(\s*\))\s*\.\s*(close|kill)\w*\s*\(", "closes the simulation"),
    (r"\bsaveState\s*\(", "writes a .sim file (it can overwrite the user's file)"),
    (r"(?i)\bclear(Solution|Mesh|Fields|History)\w*\s*\(|\bSolution\.Clear\b", "deletes solution or mesh data"),
    (r"\.(deleteObjects|removeObjects?|remove|delete)\s*\(", "deletes objects from the simulation"),
    (r"getSimulationIterator\s*\(\s*\)\s*\.\s*(run|step|runAutomation)\s*\(", "runs the solver (uses licence time)"),
]

_STRIP = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*.*?\*/', re.S)


def check_macro(source: str, allow_risky: bool = False) -> list[str]:
    """Problems that stop the macro from running (empty list means it may run)."""
    code = _STRIP.sub(lambda m: '""' if m.group(0)[0] in "\"'" else " ", source)
    problems = [f"blocked: {why}" for pat, why in BLOCKED if re.search(pat, code)]
    if not allow_risky:
        problems += [f"needs allow_risky=True: {why}" for pat, why in RISKY if re.search(pat, code)]
    if not re.search(r"\bextends\s+StarMacro\b", code):
        problems.append("the macro must contain a public class that extends StarMacro")
    return problems


def class_name(source: str) -> str:
    m = re.search(r"\bpublic\s+(?:final\s+)?class\s+(\w+)", source)
    if not m:
        raise ValueError("No 'public class <Name>' found in the macro.")
    return m.group(1)


_PS_SESSIONS = r"""
$out = @()
$seen = @{}
foreach ($c in Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue) {
  if ($c.LocalPort -lt %(lo)d -or $c.LocalPort -ge %(hi)d -or $seen[$c.LocalPort]) { continue }
  $p = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
  if (-not $p -or $p.ProcessName -notmatch 'star') { continue }
  $seen[$c.LocalPort] = 1
  $ids = Get-NetTCPConnection -State Established -RemotePort $c.LocalPort -ErrorAction SilentlyContinue |
         Where-Object { $_.OwningProcess -ne $c.OwningProcess } | Select-Object -ExpandProperty OwningProcess -Unique
  $cl = @(foreach ($id in $ids) { $q = Get-Process -Id $id -ErrorAction SilentlyContinue
          if ($q) { [pscustomobject]@{ pid = $id; process = $q.ProcessName; window_title = $q.MainWindowTitle } } })
  $out += [pscustomobject]@{ port = $c.LocalPort; server_pid = $c.OwningProcess; server_process = $p.ProcessName;
                             started = $p.StartTime.ToString('s'); clients = $cl }
}
ConvertTo-Json -InputObject @($out) -Depth 4
"""


def list_sessions() -> list[dict]:
    if os.name != "nt":
        raise NotImplementedError("Listing sessions is only implemented on Windows. Pass the port explicitly.")
    script = _PS_SESSIONS % {"lo": PORT_RANGE.start, "hi": PORT_RANGE.stop}
    res = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                         capture_output=True, text=True, timeout=60)
    data = json.loads(res.stdout) if res.stdout.strip() else []
    for s in data:
        s["clients"] = s.get("clients") or []
        titles = [c.get("window_title") or "" for c in s["clients"]]
        sim = next((t.split(" - Simcenter STAR-CCM+")[0] for t in titles if "STAR-CCM+" in t), None)
        s["simulation_from_window_title"] = sim
    return data


def _decode(b: bytes) -> str:
    for enc in ("utf-8", "cp1252"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            pass
    return b.decode("latin-1")


async def run_batch(port: int, macro: Path, timeout_s: int) -> dict:
    """Runs one macro file on the server at localhost:<port>; kills only the batch client on timeout."""
    exe = paths.batch_launcher()
    if os.name == "nt":
        # Python wraps this in cmd /c "...", so the inner quotes survive.
        proc = await asyncio.create_subprocess_shell(f'"{exe}" -host localhost:{port} -batch "{macro}"',
                                                     stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    else:
        proc = await asyncio.create_subprocess_exec(str(exe), "-host", f"localhost:{port}", "-batch", str(macro),
                                                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    timed_out = False
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        timed_out = True
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        else:
            proc.kill()
        out, _ = await proc.communicate()
    text = mask(_decode(out or b""))
    return {"exit_code": proc.returncode, "timed_out": timed_out, "output": text}


def write_macro(source: str) -> Path:
    d = Path(tempfile.gettempdir()) / "starccm-mcp" / uuid.uuid4().hex[:12]
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{class_name(source)}.java"
    f.write_text(source, encoding="utf-8")
    return f


def trim_output(text: str, max_chars: int) -> dict:
    lines = text.splitlines()
    errors = [s for s in lines if re.search(r"(?i)\b(error|exception)\b", s) and "INFO" not in s][:30]
    mcp_lines = [s[4:] for s in lines if s.startswith("MCP|")]
    body = text if len(text) <= max_chars else "...[truncated]...\n" + text[-max_chars:]
    return {"errors": errors, "tagged_lines": mcp_lines, "output": body}


INFO_MACRO = r"""
import star.common.*;
import star.base.report.*;
import star.vis.*;

public class StarccmMcpInfo extends StarMacro {
  private Simulation sim;
  private void p(String k, String v) { sim.println("MCP|" + k + "|" + v); }
  public void execute() {
    sim = getActiveSimulation();
    p("simulation", sim.getPresentationName());
    p("session_path", sim.getSessionPath());
    p("workers", String.valueOf(sim.getNumberOfWorkers()));
    p("iteration", String.valueOf(sim.getSimulationIterator().getCurrentIteration()));
    for (Region r : sim.getRegionManager().getRegions()) {
      p("region", r.getPresentationName());
      for (Boundary b : r.getBoundaryManager().getBoundaries())
        p("boundary", r.getPresentationName() + "|" + b.getPresentationName() + "|" + b.getBoundaryType().getPresentationName());
    }
    for (Object o : sim.getContinuumManager().getObjects()) {
      if (!(o instanceof PhysicsContinuum)) continue;
      PhysicsContinuum c = (PhysicsContinuum) o;
      StringBuilder m = new StringBuilder();
      for (Object x : c.getModelManager().getObjects()) m.append(((Model) x).getPresentationName()).append(";");
      p("continuum", c.getPresentationName() + "|" + m);
    }
    for (Object o : sim.get(GlobalParameterManager.class).getObjects()) {
      if (!(o instanceof ScalarGlobalParameter)) continue;
      ScalarGlobalParameter g = (ScalarGlobalParameter) o;
      ScalarPhysicalQuantity q = g.getQuantity();
      p("parameter", g.getPresentationName() + "|" + q.getDefinition() + "|" + q.getRawValue() + "|" + q.getUnits().getPresentationName());
    }
    for (Object o : sim.getReportManager().getObjects()) p("report", ((Report) o).getPresentationName());
    for (Monitor mo : sim.getMonitorManager().getMonitors()) p("monitor", mo.getPresentationName());
    for (Scene s : sim.getSceneManager().getScenes()) p("scene", s.getPresentationName());
    p("done", "ok");
  }
}
"""


def parse_info(tagged: list[str]) -> dict:
    info: dict = {"regions": [], "boundaries": [], "continua": [], "parameters": [], "reports": [], "monitors": [],
                  "scenes": []}
    for line in tagged:
        key, _, val = line.partition("|")
        parts = val.split("|")
        if key in ("simulation", "session_path", "workers", "iteration", "done"):
            info[key] = val
        elif key == "region":
            info["regions"].append(val)
        elif key == "boundary" and len(parts) == 3:
            info["boundaries"].append({"region": parts[0], "name": parts[1], "type": parts[2]})
        elif key == "continuum":
            info["continua"].append({"name": parts[0], "models": [m for m in parts[1].split(";") if m] if len(parts) > 1 else []})
        elif key == "parameter" and len(parts) == 4:
            info["parameters"].append({"name": parts[0], "definition": parts[1], "value": parts[2], "units": parts[3]})
        elif key in ("report", "monitor", "scene"):
            info[key + "s"].append(val)
    return info
