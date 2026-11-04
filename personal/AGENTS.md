# personal kit: notes for agents

An acq `hybrid/v1` skill kit. Start with [`README.md`](README.md).

- **Do not hand-edit** anything under `files/home/.agents/skills/` except
  `paseo-first-mate/`. The rest is Matt Pocock's work, copied by
  `scripts/vendor-pocock-skills` and checked against `vendor/mattpocock-skills.json`.
  To change it, change the script. Read
  [`docs/vendored-skills.md`](docs/vendored-skills.md) first: it lists every local
  difference from upstream and how to update.
- **Credit travels with the copies.** Keep [`NOTICE`](NOTICE) and the files in
  `files/home/.agents/licenses/`. New third-party material needs its notice, a
  `THIRD_PARTY` entry, and a line in `docs/vendored-skills.md`.
- **Never install a skill as `code-review`.** The playbook kit owns that name. Upstream's
  is `pocock-code-review`.
- **`spec.yaml`:** the block between the `BEGIN vendored` and `END vendored` markers is
  generated. Records above it are hand-written and need a declared mode that
  `scripts/verify` checks. Every file under `files/` must have a record, because msb
  copies only listed files.
- **Check your work:** `scripts/verify` (offline) and, from the repository root,
  `python scripts/run-kit-tests.py personal`. Both need `python3`; `shellcheck` and `acq`
  are used when installed.
- The kit has no `commands`, no `caps.network` and no `agent:` block on purpose. Every
  payload is dropped at its final path; do not add a startup step to link or fetch.
