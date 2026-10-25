# Security Policy

## Reporting a vulnerability

Please report security issues privately. Do **not** open a public issue for a
vulnerability.

- **Preferred:** use GitHub private vulnerability reporting on this repository —
  **Security** tab → **Report a vulnerability**.
  <https://github.com/mogul/agentic-coding-kits/security/advisories/new>
- **Alternative:** email the maintainer at <bmogilefsky@gmail.com> with
  "agentic-coding-kits security" in the subject.

Include the affected file or kit, a description of the impact, and a minimal
reproduction if you have one. Please allow a reasonable window for a fix before
public disclosure.

## Scope

This repository contains provider kit metadata: facts, a neutral model catalog,
a host-side normalizer, tests, and docs. It contains **no credentials**.

Relevant classes of issue include:

- A credential, token, or key committed to the repository.
- A catalog or spec that could redirect a credential or provider host.
- A normalizer path-traversal or arbitrary-write issue when run host-side.
- A trust-boundary weakness in how a kit's snapshot or facts are documented or
  consumed.
- A supply-chain issue in the kit refs documented here (for example, encouraging
  a mutable branch ref instead of a pinned SHA).

Issues in `acq` itself, in `agentic-coding-patterns`, or in OpenCode Go should be
reported to those projects.

## Supported versions

This repository is a rolling collection of kits on `main`. Security fixes land on
`main`; consumers should pin a full commit SHA and update deliberately.
