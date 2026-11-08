# starccm-mcp
# © 2026 RHerAle
# SPDX-License-Identifier: GPL-3.0-only
# Additional terms under section 7 of the GPL apply: see NOTICE.
"""MCP server for Simcenter STAR-CCM+.

Four groups of tools:
- starccm_sim_*      read a .sim file directly (no STAR-CCM+, no licence, read-only)
- starccm_log_*      read solver output logs
- starccm_docs_* / starccm_api_lookup   search the user guide and Java API reference of the local install
- starccm_session_* / starccm_run_macro  talk to a STAR-CCM+ server that is already running
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from . import docs, logs, paths, session, simfile

mcp = MCPServer("starccm_mcp", instructions=(
    "Tools for Simcenter STAR-CCM+. starccm_sim_* read .sim files without a licence; starccm_log_* read solver "
    "logs; starccm_docs_* and starccm_api_lookup search the local documentation; starccm_session_* and "
    "starccm_run_macro act on a running simulation. Before any macro: run starccm_session_info, check every "
    "API call with starccm_api_lookup, and ask the user before setting allow_risky."))


def _ro(title: str) -> ToolAnnotations:
    return ToolAnnotations(title=title, read_only_hint=True, destructive_hint=False, idempotent_hint=True,
                           open_world_hint=False)

SimPath = Annotated[str, Field(description="Absolute path of a .sim file, e.g. C:\\cases\\wing.sim", min_length=4)]


def _json(data: Any) -> str:
    return json.dumps(data, indent=1, ensure_ascii=False, default=str)


def _error(e: Exception) -> str:
    """Message for a failed tool call; raised as ToolError so the client sees is_error=True."""
    if isinstance(e, ToolError):
        return str(e)
    hints = {
        FileNotFoundError: "Check the path; use an absolute path.",
        ValueError: "The file may not be a STAR-CCM+ .sim, or the value is not what the tool expected.",
    }
    hint = next((h for t, h in hints.items() if isinstance(e, t)), "")
    msg = e.args[0] if isinstance(e, KeyError) and e.args else e
    return f"Error: {msg}" + (f" {hint}" if hint else "")


async def _sim(path: str) -> simfile.SimFile:
    return await asyncio.to_thread(simfile.open_sim, path)


# ---- .sim files -------------------------------------------------------------------------------------
@mcp.tool(name="starccm_sim_overview", annotations=_ro("Overview of a .sim file"))
async def starccm_sim_overview(
    path: SimPath,
    history: Annotated[int, Field(description="How many entries of the save history to include", ge=0, le=50)] = 5,
) -> str:
    """Summary of a STAR-CCM+ .sim file read directly from disk, without STAR-CCM+ or a licence.

    Returns JSON with: STAR-CCM+ version that saved it, current iteration, volume mesh size (cells, faces,
    vertices), regions, number of boundaries, physics continua with their models, global parameters,
    reports, monitors, mesh operations, scenes, stopping criteria (used/satisfied and their limits) and the
    last save-history entries. Start here, then use starccm_sim_parameters, starccm_sim_boundaries,
    starccm_sim_monitors or starccm_sim_object for details. The file is never modified.
    """
    try:
        sim = await _sim(path)
        return _json(simfile.overview(sim, history))
    except Exception as e:
        raise ToolError(_error(e)) from e


@mcp.tool(name="starccm_sim_parameters", annotations=_ro("Global parameters of a .sim"))
async def starccm_sim_parameters(path: SimPath) -> str:
    """Global parameters (Tools > Parameters) of a .sim file: name, definition, stored value and units.

    Note: the stored value of an expression is the last one STAR-CCM+ evaluated; after an edit that was not
    re-evaluated it can be stale. The definition is always the current one.
    """
    try:
        return _json(simfile.parameters(await _sim(path)))
    except Exception as e:
        raise ToolError(_error(e)) from e


@mcp.tool(name="starccm_sim_boundaries", annotations=_ro("Boundaries and their conditions"))
async def starccm_sim_boundaries(
    path: SimPath,
    region: Annotated[str | None, Field(description="Only boundaries of this region (case-insensitive)")] = None,
    name: Annotated[str | None, Field(description="Only the boundary with this name (case-insensitive)")] = None,
) -> str:
    """Boundary types and physics values of every boundary in a .sim file.

    For each boundary: region, name, type (e.g. FreeStreamBoundary, WallBoundary, StagnationBoundary),
    selected options and the active values with method, definition, value and units (e.g. Mach number
    '${Minlet}' = 0.8). Options are stored as indices; when the local Java API reference is available they
    are translated to their labels (e.g. FlowDirectionOption -> 'Components').
    """
    try:
        sim = await _sim(path)
        out = simfile.boundaries(sim, region, name)
        labels: dict[str, list[str] | None] = {}
        for b in out:
            named = {}
            for opt, i in b["options_selected_index"].items():
                if opt not in labels:
                    labels[opt] = await asyncio.to_thread(docs.option_names, opt)
                lab = labels[opt]
                named[opt] = lab[i] if lab and isinstance(i, int) and 0 <= i < len(lab) else f"index {i}"
            b["options"] = named
        return _json(out) if out else "No boundaries matched. Use starccm_sim_overview to see region names."
    except Exception as e:
        raise ToolError(_error(e)) from e


@mcp.tool(name="starccm_sim_monitors", annotations=_ro("Monitors and their history"))
async def starccm_sim_monitors(
    path: SimPath,
    name: Annotated[str | None, Field(description="Monitor name (e.g. 'CD Monitor', 'Continuity'). "
                                                  "Omit to list all monitors.")] = None,
    last: Annotated[int, Field(description="Number of most recent samples to return", ge=1, le=5000)] = 20,
    stride: Annotated[int, Field(description="Take every n-th sample (the last one is always included)", ge=1)] = 1,
) -> str:
    """Residual and report monitors stored in a .sim file.

    Without `name`: list of monitors with class, linked report, current value and number of stored samples.
    With `name`: the stored history (x = iteration or time, y = monitor value) for the last `last` samples.
    Use it to check convergence or read the final value of a force coefficient without opening STAR-CCM+.
    """
    try:
        sim = await _sim(path)
        if not name:
            return _json(simfile.monitors(sim))
        return _json(await asyncio.to_thread(simfile.monitor_series, sim, name, last, stride))
    except Exception as e:
        raise ToolError(_error(e)) from e


@mcp.tool(name="starccm_sim_find", annotations=_ro("Search objects in a .sim"))
async def starccm_sim_find(
    path: SimPath,
    pattern: Annotated[str, Field(description="Regular expression, case-insensitive (e.g. '^CD$', 'Report$')", min_length=1)],
    where: Annotated[Literal["name", "class", "text"], Field(
        description="Match against the object name, its class, or the whole raw record")] = "name",
    limit: Annotated[int, Field(ge=1, le=200)] = 30,
    offset: Annotated[int, Field(ge=0)] = 0,
) -> str:
    """Finds objects in a .sim file by name, class or raw text. Returns record numbers for starccm_sim_object."""
    try:
        return _json(simfile.find(await _sim(path), pattern, where, limit, offset))
    except Exception as e:
        raise ToolError(_error(e)) from e


@mcp.tool(name="starccm_sim_object", annotations=_ro("Settings of one object in a .sim"))
async def starccm_sim_object(
    path: SimPath,
    record: Annotated[int | None, Field(description="Record number from starccm_sim_find")] = None,
    name: Annotated[str | None, Field(description="Exact object name, used if record is not given (e.g. 'CD')")] = None,
    depth: Annotated[int, Field(description="How many levels of referenced objects to expand", ge=0, le=4)] = 1,
) -> str:
    """All settings of one object (report, mesh operation, physics model, solver, criterion...).

    References are resolved: quantities show value, units and definition; options show the selected index;
    other objects show their name and class, expanded to `depth` levels.
    """
    try:
        sim = await _sim(path)
        if record is None:
            if not name:
                raise ToolError("Error: give `record` or `name`.")
            hits = [r for r in sim.ids(*sim.by_class) if sim.rec(r).get("PresentationName") == name]
            if not hits:
                raise ToolError(f"Error: no object named {name!r}. Try starccm_sim_find with where='name'.")
            if len(hits) > 1:
                return _json({"ambiguous": [{"record": r, "class": sim.cls(r)} for r in hits[:30]]})
            record = hits[0]
        d = sim.rec(record)
        if not d:
            raise ToolError(f"Error: record {record} does not exist or could not be parsed.")
        return _json({"record": record, "class": sim.cls(record), "name": d.get("PresentationName"),
                      "settings": sim.settings(record, depth)})
    except Exception as e:
        raise ToolError(_error(e)) from e


# ---- logs -------------------------------------------------------------------------------------------
LogPath = Annotated[str | None, Field(description="Path of a log file. Omit to use the desktop client's messages.log.")]


@mcp.tool(name="starccm_log_summary", annotations=_ro("Summary of a solver log"))
async def starccm_log_summary(
    path: LogPath = None,
    last_rows: Annotated[int, Field(description="Iteration rows to return from the end", ge=1, le=500)] = 10,
) -> str:
    """Parses a STAR-CCM+ output log: iteration table and solver events.

    Returns the column names, the first and last iteration rows, grouped events with counts and the first and
    last iteration where they happened (AMG divergence, reversed flow, limited cells, errors, warnings,
    stopping criteria, saves) and the last lines of text. Licence keys and servers are masked.
    """
    try:
        p = Path(path) if path else paths.default_log()
        text = await asyncio.to_thread(logs.read_text, p)
        return _json({"file": str(p), **logs.summarize(text, last_rows)})
    except Exception as e:
        raise ToolError(_error(e)) from e


@mcp.tool(name="starccm_log_tail", annotations=_ro("Tail of a log"))
async def starccm_log_tail(
    path: LogPath = None,
    lines: Annotated[int, Field(ge=1, le=2000)] = 100,
    grep: Annotated[str | None, Field(description="Keep only lines matching this regular expression")] = None,
) -> str:
    """Last lines of a STAR-CCM+ log, optionally filtered. Licence keys and servers are masked."""
    try:
        p = Path(path) if path else paths.default_log()
        text = await asyncio.to_thread(logs.read_text, p)
        return logs.tail(text, lines, grep) or "(no matching lines)"
    except Exception as e:
        raise ToolError(_error(e)) from e


# ---- documentation ----------------------------------------------------------------------------------
@mcp.tool(name="starccm_docs_search", annotations=_ro("Search the STAR-CCM+ user guide"))
async def starccm_docs_search(
    query: Annotated[str, Field(description="Words that must all appear, e.g. 'free stream reference pressure'", min_length=2)],
    limit: Annotated[int, Field(ge=1, le=50)] = 10,
    regex: Annotated[bool, Field(description="Treat query as one regular expression")] = False,
) -> str:
    """Searches the HTML user guide installed with STAR-CCM+ (built into a local index on first use, a few
    seconds). Returns page ids, titles and a snippet; read a page with starccm_docs_page."""
    try:
        return _json(await asyncio.to_thread(docs.search_manual, query, limit, regex))
    except Exception as e:
        raise ToolError(_error(e)) from e


@mcp.tool(name="starccm_docs_page", annotations=_ro("Read a user-guide page"))
async def starccm_docs_page(
    page_id: Annotated[str, Field(description="Page id from starccm_docs_search, e.g. GUID-997C51B2-E245-4D2D-87A9-4CDEAA8D90AE")],
    start: Annotated[str | None, Field(description="Start at the first occurrence of this text")] = None,
    offset: Annotated[int, Field(ge=0)] = 0,
    max_chars: Annotated[int, Field(ge=200, le=30000)] = 6000,
) -> str:
    """Plain text of one page of the local user guide, paginated with offset/max_chars."""
    try:
        return _json(await asyncio.to_thread(docs.read_page, page_id, start, offset, max_chars))
    except Exception as e:
        raise ToolError(_error(e)) from e


@mcp.tool(name="starccm_api_lookup", annotations=_ro("Look up the STAR-CCM+ Java API"))
async def starccm_api_lookup(
    name: Annotated[str, Field(description="'Class', 'Class.method' or 'Outer.Inner', e.g. 'RegionManager.getRegions', "
                                           "'FlowDirectionOption.Type'")],
    contains: Annotated[str | None, Field(description="With a bare class: only members whose signature contains this")] = None,
    limit: Annotated[int, Field(ge=1, le=200)] = 40,
) -> str:
    """Checks a class or method against the local Java API reference before writing a macro: package,
    inheritance, exact signatures (following inherited methods to the class that declares them), or a list
    of similar class names when the name is wrong."""
    try:
        return _json(await asyncio.to_thread(docs.api_lookup, name, contains, limit))
    except Exception as e:
        raise ToolError(_error(e)) from e


# ---- live sessions ----------------------------------------------------------------------------------
@mcp.tool(name="starccm_session_list", annotations=_ro("List running STAR-CCM+ servers"))
async def starccm_session_list() -> str:
    """Running STAR-CCM+ servers on this machine (Windows): port, server process, start time, connected
    clients and, when a GUI is connected, the simulation name from its window title. Licence data is never
    returned."""
    try:
        data = await asyncio.to_thread(session.list_sessions)
        return _json(data) if data else "No STAR-CCM+ server is listening on ports 47827-47999."
    except Exception as e:
        raise ToolError(_error(e)) from e


async def _check_port(port: int, expected_sim: str | None) -> str | None:
    sessions = await asyncio.to_thread(session.list_sessions)
    match = next((s for s in sessions if s["port"] == port), None)
    if not match:
        return f"No STAR-CCM+ server on port {port}. Running: {[s['port'] for s in sessions]}"
    title_sim = match["simulation_from_window_title"]
    if expected_sim and title_sim is None:
        return (f"No GUI is connected to port {port}, so '{expected_sim}' cannot be confirmed from a window title. "
                "Run starccm_session_info, compare the name, then call again without expected_sim. Nothing was run.")
    if expected_sim and title_sim != expected_sim:
        return f"Port {port} has '{title_sim}' open, not '{expected_sim}'. Nothing was run."
    return None


@mcp.tool(name="starccm_session_info", annotations=_ro("Inspect a running simulation"))
async def starccm_session_info(
    port: Annotated[int, Field(description="Server port from starccm_session_list", ge=1024, le=65535)],
    timeout_s: Annotated[int, Field(ge=30, le=600)] = 180,
) -> str:
    """Runs a built-in read-only macro on the server at localhost:<port> and returns the simulation name and
    path, workers, current iteration, regions and boundaries with types, continua and models, global
    parameters (definition, value, units), reports, monitors and scenes. It takes some seconds because a
    batch client has to start. Use it to confirm which simulation is open before running any other macro."""
    try:
        problem = await _check_port(port, None)
        if problem:
            raise ToolError(f"Error: {problem}")
        res = await session.run_batch(port, await asyncio.to_thread(session.write_macro, session.INFO_MACRO), timeout_s)
        trimmed = session.trim_output(res["output"], 4000)
        info = session.parse_info(trimmed["tagged_lines"])
        if info.get("done") != "ok":
            raise ToolError(_json({"error": "the info macro did not finish", "timed_out": res["timed_out"],
                                   "errors": trimmed["errors"], "output_tail": trimmed["output"]}))
        return _json(info)
    except Exception as e:
        raise ToolError(_error(e)) from e


@mcp.tool(name="starccm_run_macro", annotations=ToolAnnotations(
    title="Run a Java macro on a running simulation", read_only_hint=False, destructive_hint=True,
    idempotent_hint=False, open_world_hint=False))
async def starccm_run_macro(
    port: Annotated[int, Field(description="Server port from starccm_session_list", ge=1024, le=65535)],
    source: Annotated[str | None, Field(description="Full Java source of the macro: a public class extending "
                                                    "StarMacro, with execute()")] = None,
    macro_path: Annotated[str | None, Field(description="Path of an existing .java macro (instead of source)")] = None,
    expected_sim: Annotated[str | None, Field(description="Refuse to run unless this simulation name is the one open on "
                                                          "the port (checked against the GUI window title)")] = None,
    allow_risky: Annotated[bool, Field(description="Allow operations that save, delete, close, run the solver or touch "
                                                   "3D-CAD. Only after the user agreed to that specific action.")] = False,
    timeout_s: Annotated[int, Field(ge=10, le=7200)] = 600,
    max_chars: Annotated[int, Field(description="Characters of output to return from the end", ge=500, le=100000)] = 12000,
) -> str:
    """Runs a Java macro on the STAR-CCM+ server at localhost:<port> through a batch client. The server, its
    GUI and the open simulation stay running; on timeout only the batch client is killed.

    Before running, the macro is checked. Always refused: Java reflection (getMethods/invoke/setAccessible),
    Class.forName, System.exit, starting processes. A reflective read-only macro once crashed a parallel
    server when it reached unloaded 3D-CAD sketches. Refused unless allow_risky=True: 3D-CAD access,
    saveState, deleting objects, clearing solution or mesh, closing the simulation, running the solver.

    Good practice: call starccm_session_info first; verify every class and method with starccm_api_lookup;
    write simple macros like the ones STAR-CCM+ records; print results with sim.println(...), and prefix
    lines with 'MCP|' to get them back in `tagged_lines`.
    """
    try:
        if bool(source) == bool(macro_path):
            raise ToolError("Error: give exactly one of `source` or `macro_path`.")
        if macro_path:
            mp = Path(macro_path)
            if mp.suffix != ".java" or not mp.is_file():
                raise ToolError(f"Error: {macro_path} is not an existing .java file.")
            src = mp.read_text(encoding="utf-8", errors="replace")
            if session.class_name(src) != mp.stem:
                raise ToolError(f"Error: the public class must be named like the file ({mp.stem}).")
        else:
            src = source or ""
        problems = session.check_macro(src, allow_risky)
        if problems:
            raise ToolError(_json({"refused": True, "problems": problems}))
        problem = await _check_port(port, expected_sim)
        if problem:
            raise ToolError(f"Error: {problem}")
        target = Path(macro_path) if macro_path else await asyncio.to_thread(session.write_macro, src)
        res = await session.run_batch(port, target, timeout_s)
        return _json({"exit_code": res["exit_code"], "timed_out": res["timed_out"], "macro": str(target),
                      **session.trim_output(res["output"], max_chars)})
    except Exception as e:
        raise ToolError(_error(e)) from e


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
