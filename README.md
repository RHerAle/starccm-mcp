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
| `starccm_session_list` | Running servers: port, clients and open simulation (Windows) | no |
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
- **Licence data is masked.** STAR-CCM+ puts the Power-on-Demand key and the licence server on the command
  line of every server process, and logs can repeat them. Log text and macro output are masked by
  `masking.py` as a whole, before any filtering or truncation; process command lines are never returned.
  The masking works by patterns, so treat it as a strong safeguard, not a guarantee.
- **The log tools read any text file you point them at.** They are meant for STAR-CCM+ logs; the path is
  not restricted.
- **Macros are checked before they run, but the check is not a sandbox.** It reads the source with
  patterns to catch an assistant's mistakes before they reach your live session. A macro that runs has your
  full rights and the server's: it can write files, open connections or check out licences. Never run a
  macro you do not trust. The rules come from a real accident: a "read-only" macro that called getters by
  reflection reached unloaded 3D-CAD sketches on a parallel server. The server died with
  `Non-recoverable ... isSerialCritical` and took the open simulation with it.
  - Refused: Java reflection, class loading, `System.exit` and `System.getenv`, `Runtime` and processes,
    network classes and script engines.
  - Refused unless `allow_risky=True`: 3D-CAD access, `saveState`, deleting or clearing objects and data,
    closing the simulation, running the solver, meshing and writing files. The assistant should only set
    it after you agree to that specific action.
  - Known limits: the patterns look at names, not types, so they can be evaded (for example by storing the
    simulation or a `Class` object in another variable first), file writes through STAR-CCM+'s own APIs are
    only partly recognised, and Java has more ways to reach the outside than any list can name.
  - `expected_sim` refuses to run if the window on that port shows a different simulation.
  - On a timeout, only the batch client is killed. The server and your GUI keep running.
- **The MCP server itself** never starts a STAR-CCM+ server, never checks out a licence and makes no
  network connections. What a macro does once it runs is up to the macro.

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
comprobaciones para evitar errores que la tumben (no son un sandbox). Instalación y uso, arriba. Licencia
GPL-3.0-only: si lo redistribuyes, modificado o no, tu versión debe seguir siendo GPL, conservar la atribución
a este proyecto en sus avisos legales y, si está modificada, indicarlo (detalles en `NOTICE`).

## Licence

© 2026 RHerAle. Code under GPL-3.0-only ([`LICENSE`](LICENSE)), with additional terms under section 7 of the
GPL ([`NOTICE`](NOTICE)): every copy and every modified version must keep the author attribution in its
legal notices, and a modified version must be marked as different from the original and must not be
presented as the original.

## Forks and variants

If you publish a variant, please make it a GitHub fork and add it to [`VARIANTS.md`](VARIANTS.md) with a pull
request, so other users can find it. This is a request, not a licence condition.

## Contributing

Pull requests are welcome, with no agreement to sign: contributions are licensed under the same terms as
the project, and each commit carries a `Signed-off-by` line (`git commit -s`). See
[`CONTRIBUTING.md`](CONTRIBUTING.md).
