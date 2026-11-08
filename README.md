# starccm-mcp

An unofficial [MCP](https://modelcontextprotocol.io) server for **Simcenter STAR-CCM+**. It lets an AI assistant
such as Claude Code, Claude Desktop or any other MCP client:

- **read a `.sim` file without STAR-CCM+ and without a licence**: version, mesh size, regions, boundary
  conditions with their values, global parameters, physics models, reports, stopping criteria and the full
  history of every monitor;
- **read solver logs**: the iteration table, AMG divergences, reversed flow, limited cells and stopping
  criteria, with licence keys masked;
- **search the documentation of your own installation**, including the user guide and the Java API reference,
  so macros are written against methods that exist;
- **run Java macros on a simulation you already have open**, through a batch client, with guard rails.

It was written by a student who needed to understand someone else's `.sim` at midnight without a licence
seat free. If you have ever had to guess why a case diverged or what a teammate set on a boundary, this is
for you.

> Not affiliated with, endorsed by or supported by Siemens. Simcenter and STAR-CCM+ are trademarks of
> Siemens Digital Industries Software. This repository contains no Siemens code or documentation: the
> documentation tools read the files of *your* local installation.

## Tools

| Tool | What it does | Needs STAR-CCM+ installed |
|---|---|---|
| `starccm_sim_overview` | Version, iteration, mesh size, regions, continua and models, parameters, reports, monitors, stopping criteria and save history | no |
| `starccm_sim_parameters` | Global parameters with definition, value and units | no |
| `starccm_sim_boundaries` | Boundary types, options and active values (for example Mach `${Minlet}` = 0.8) | no¹ |
| `starccm_sim_monitors` | List of monitors, or the stored history of one (residuals, CD, CL…) | no |
| `starccm_sim_find` / `starccm_sim_object` | Find any object and show all its settings with references resolved | no |
| `starccm_log_summary` / `starccm_log_tail` | Iteration table, grouped solver events, filtered tail | no |
| `starccm_docs_search` / `starccm_docs_page` | Full-text search of the local user guide | yes |
| `starccm_api_lookup` | Classes, inheritance and exact method signatures from the local Java API reference | yes |
| `starccm_session_list` | Running servers: port, clients and open simulation (Windows) | yes |
| `starccm_session_info` | Read-only snapshot of a running simulation | yes |
| `starccm_run_macro` | Run a checked Java macro on a running simulation | yes |

¹ Option names, such as `Components` instead of `index 1`, are looked up in the local Java API reference when it is installed.

## Install

You need Python 3.10 or newer. The `.sim` and log tools are plain Python and run anywhere. The session tools
are Windows-only for now.

```bash
git clone https://github.com/RHerAle/starccm-mcp
cd starccm-mcp
python -m venv .venv
.venv\Scripts\pip install -e .
```

Add it to **Claude Code**:

```bash
claude mcp add starccm -- C:\path\to\starccm-mcp\.venv\Scripts\starccm-mcp.exe
```

Or to **Claude Desktop**, in `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "starccm": { "command": "C:\\path\\to\\starccm-mcp\\.venv\\Scripts\\starccm-mcp.exe" }
  }
}
```

The installation is found under `C:\Program Files\Siemens\*\STAR-CCM+*`. If yours is somewhere else, set
`STARCCM_HOME` to the folder that contains `star\` and `doc\`.

## Safety

- **`.sim` files are only opened for reading.**
- **Licence data never leaves the server.** STAR-CCM+ puts the Power-on-Demand key and the licence server on
  the command line of every server process, and logs can repeat them. Every log line, process line and
  macro output passes through `masking.py` before it is returned.
- **Macros are checked before they run.** The rules come from a real accident: a "read-only" macro that
  called getters by reflection reached unloaded 3D-CAD sketches on a parallel server. The server died with
  `Non-recoverable ... isSerialCritical` and took the open simulation with it.
  - Always refused: reflection (`getMethods`, `invoke`, `setAccessible`), `Class.forName`, `System.exit`,
    and starting processes.
  - Refused unless `allow_risky=True`: 3D-CAD access, `saveState`, deleting objects, clearing the solution
    or mesh, closing the simulation, and running the solver, which spends licence time. The assistant
    should only set it after you agree to that specific action.
  - `expected_sim` refuses to run if the window on that port shows a different simulation.
  - On a timeout, only the batch client is killed. The server and your GUI keep running.
- This server never starts a STAR-CCM+ server, never checks out a licence and makes no network
  connections other than to `localhost`.

## How the `.sim` reader works

Siemens does not document the format. This is what was observed on files saved by STAR-CCM+ 2502 (20.02):

- The first line is a dict with `'StatePosition': N`.
- From byte N to the end of the file, each line is one object written as a Python-like dict, and object
  `r` sits on line `r + 2`.
- Integers with an `L` suffix are usually references to other objects.
- Monitor histories are `MasterArray<Float8>` records. Their `dataKey` is the absolute byte offset of a
  one-line header followed by little-endian doubles.

Only the object state is parsed, never the mesh or the solution arrays, so a 250 MB `.sim` opens in about
0.3 s.

## Status and limitations

- Tested with STAR-CCM+ **2502 (20.02.008)** on Windows 11. Other versions are untested; reports are welcome.
- Solution fields stored in the `.sim`, such as density on a boundary, are not exposed yet.
- An expression's stored value is the last one STAR-CCM+ evaluated; the definition is always current.
- The session list reads the open simulation from the GUI window title. Without a GUI, use
  `starccm_session_info`.

## Development

```bash
.venv\Scripts\pip install -e ".[test]"
.venv\Scripts\python -m pytest
```

The tests build a tiny synthetic `.sim` and a synthetic log, so they need neither STAR-CCM+ nor real files.

## En español

Servidor MCP no oficial para STAR-CCM+. Lee un `.sim` sin abrir STAR-CCM+ ni gastar licencia: contornos con
sus valores, parámetros, modelos, criterios de parada e historial de los monitores. También lee el log, busca
en el manual y el javadoc de tu propia instalación y lanza macros contra una sesión abierta, con
protecciones para no tumbarla. Instalación y uso, arriba. Licencia GPL-3.0-only: si lo modificas o lo
redistribuyes, tu versión debe seguir siendo GPL, citar este proyecto e indicar que es una versión
modificada (detalles en `NOTICE`).

## Licence

© 2026 RHerAle. Code under GPL-3.0-only ([`LICENSE`](LICENSE)), with additional terms under section 7 of the
GPL ([`NOTICE`](NOTICE)): every copy and every modified version must keep the attribution
*"Based on starccm-mcp by RHerAle, https://github.com/RHerAle/starccm-mcp"*, and a modified version must say
that it is one and must not be presented as the original.

A licence for use in a closed product can be arranged: contact the author through
<https://github.com/RHerAle>.

## Forks and variants

If you adapt it, publish your version as a GitHub fork and add it to [`VARIANTS.md`](VARIANTS.md) with a pull
request, so other users can find it.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) and the agreement in [`FLA.md`](FLA.md).
