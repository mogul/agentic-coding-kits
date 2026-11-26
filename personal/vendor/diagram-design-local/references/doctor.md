---
title: "Diagram Design readiness"
description: "Passive readiness checks without launching browsers or installing software"
status: canonical
tier: 2
---

# Readiness

HTML/SVG generation and import helpers need Python 3 and no extra packages.
Do not launch a browser to diagnose readiness. PNG is BLOCKED unless the human
approves an export and a separately provisioned runtime passes the guard's checks.
See [export.md](export.md). Never install dependencies automatically.
