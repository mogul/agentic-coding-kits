---
title: "Guarded Diagram Design export"
description: "Manual SVG and approved isolated PNG export"
status: canonical
tier: 2
---

# Export

Read [local-policy.md](local-policy.md) first. Keep the approved project as cwd.
Inputs and new outputs must be relative nonsymlink paths within that project.
Existing outputs are refused; choose a new name or obtain separate deletion approval.

SVG, with system fonts and no browser:

```text
python3 <skill-dir>/scripts/export_diagram.py docs/diagram.html docs/diagram.svg
```

PNG, only after the human approves this specific export in the current session:

The initial release gate is closed. This command currently reports BLOCKED even
with a runtime: live Chromium/sandbox/aggregate-budget validation is still required.

```text
python3 <skill-dir>/scripts/export_diagram.py docs/diagram.html docs/diagram.png --approve-browser-export --runtime /opt/diagram-design-runtime --scale 2
```

Runtime provisioning is separate. The guard checks input size/depth/resources,
the pinned controller, pixel area, and the upstream offline quality checker before
any browser launch. It passes a snapshot, not the live source, to a network-isolated
read-only Bubblewrap process. A failed preflight produces no export. A missing or
unvalidated browser runtime reports BLOCKED; no automatic installation occurs.

Exports contain only the SVG diagram, not editorial headers/cards. PNG captures
the complete static frame of motion HTML, at scale 1–4 (up to 16 million pixels).
For intermediate frames or full-page capture, request a separately reviewed change.

The helper prints JSON audit events, timestamps and input/output hashes without
diagram contents. Preserve its errors and warnings. Successful SVG extraction is
not a guarantee that arbitrary input can safely be inlined into an authenticated app.
