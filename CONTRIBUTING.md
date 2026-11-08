# Contributing to starccm-mcp

starccm-mcp is an unofficial MCP server for Simcenter STAR-CCM+. It is published
under GPL-3.0-only with the additional terms in [NOTICE](NOTICE). Bug reports,
questions and reports of which STAR-CCM+ versions it works with are welcome as
issues, in English or Spanish.

## Sending code

Open a pull request. Nothing has to be signed and nobody has to be e-mailed.

- **Licence of your contribution.** What you contribute is licensed under the
  same terms as the project: GPL-3.0-only plus the additional terms in NOTICE.
  This is the usual "inbound = outbound" rule, and section D.6 of the GitHub
  Terms of Service states it for every repository with a licence. You keep the
  copyright in your contribution.
- **Sign-off.** Every commit must carry a `Signed-off-by` line, which you add
  with `git commit -s`. With it you certify the
  [Developer Certificate of Origin 1.1](https://developercertificate.org/): that
  you wrote the change or otherwise have the right to submit it under this
  licence. The sign-off uses the name and e-mail of your git configuration; your
  GitHub `noreply` address is fine.
- **Credit.** Your commits keep your name. If you want to appear in
  [AUTHORS](AUTHORS), add yourself in the same pull request.

## Rules for code

- Nothing from Siemens in the repository: no STAR-CCM+ code, no text copied from
  the user guide or the Java API reference. The documentation tools read the
  user's own installation.
- No licence data, ever: no Power-on-Demand keys, licence servers or IP
  addresses, in code, tests, issues or history. Every text a tool returns goes
  through `masking.py`.
- No real `.sim` files or logs in the repository. Tests build synthetic ones
  (see `tests/conftest.py`).
- Every parser change comes with a test that would fail without it.
- A new macro capability must keep the checks in `session.py`: reflection stays
  blocked, and anything that saves, deletes, closes, runs the solver or touches
  3D-CAD needs `allow_risky`.
- Say which STAR-CCM+ version you tested with.
- New Python files start with the same four-line header as the others.
- English in code and documentation.
