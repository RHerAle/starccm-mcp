# Contributing to starccm-mcp

starccm-mcp is an unofficial MCP server for Simcenter STAR-CCM+. It is published
under GPL-3.0-only with the additional terms in [NOTICE](NOTICE). Bug reports,
questions and reports of which STAR-CCM+ versions it works with are welcome as
issues, in English or Spanish.

## Before you send code

External contributions that constitute a copyrightable work are accepted only
under a signed Fiduciary Licence Agreement ([FLA.md](FLA.md)). In short:

- You assign your exploitation rights in the contribution to the project owner,
  exclusively and free of charge.
- The owner undertakes to keep your contribution available under a free software
  licence (today GPL-3.0-only) and to credit you under the name or pseudonym you
  choose, in [AUTHORS](AUTHORS).
- The owner may also license the project, your contribution included, under
  other terms, including commercial ones.
- You keep a full licence to use your own contribution for any purpose.
- The agreement is governed by Spanish law; the Spanish text is binding and an
  English translation is provided.

How to sign: write to [PENDING: contact address]. You will receive the agreement
with the owner's identification filled in. Return Annex A signed (electronic or
scanned handwritten signature) from the e-mail address you state in it. If you are
employed and the contribution relates to your job, include Annex B signed by your
employer. One signature covers all your future pull requests.

Pull requests that need the FLA are not merged without it.

## What does not need the FLA

Typo and formatting fixes, identifier renames, trivial changes of one or a few
lines dictated by their function, and factual data without creative selection.
These are not copyrightable works and are merged under the project licence.
When in doubt, the maintainer will ask for the signature.

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
- English in code and documentation.
