import test from "node:test"
import assert from "node:assert/strict"
import { readFile, rm } from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"

import { OPENAI_COMPATIBLE_MODEL_IDS, normalizeCatalog } from "../scripts/normalize-catalog.mjs"

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const fixturePath = path.join(__dirname, "fixtures/normalize-source.json")
const snapshotPath = path.join(__dirname, "../files/home/opencode-go/model-catalog-snapshot.json")

async function readFixture() {
  return JSON.parse(await readFile(fixturePath, "utf8"))
}

test("normalizeCatalog emits the acq-neutral-model-catalog/v1 envelope", async () => {
  const neutral = normalizeCatalog(await readFixture())

  assert.equal(neutral.schemaVersion, "acq-neutral-model-catalog/v1")
  assert.equal(neutral.providerId, "opencode-go")
  assert.equal(neutral.models.length, 18)
})

test("normalizeCatalog covers exactly the OpenAI-compatible OpenCode Go models", async () => {
  const { models } = normalizeCatalog(await readFixture())

  assert.deepEqual(
    models.map((model) => model.id),
    OPENAI_COMPATIBLE_MODEL_IDS,
  )
})

test("normalizeCatalog reuses the neutral field names verbatim and drops endpoint-envelope fields", async () => {
  const { models } = normalizeCatalog(await readFixture())
  const kimi = models.find((model) => model.id === "kimi-k3.1-pro")

  assert.ok(kimi, "kimi-k3.1-pro should be present")
  assert.equal(kimi.name, "Kimi K3.1 Pro")
  assert.equal(kimi.contextWindow, 1048576)
  assert.equal(kimi.maxOutputTokens, 131072)
  assert.deepEqual(kimi.cost, { input: 2, output: 10, cacheRead: 0.2, cacheWrite: 2 })

  // The live endpoint's envelope fields are not part of the neutral shape.
  for (const key of ["object", "created", "owned_by", "capturedAt", "note"]) {
    assert.equal(key in kimi, false, `${key} must be dropped`)
  }
})

test("normalizeCatalog passes cost through UNCHANGED (per-million-token, no /1e6 transform)", async () => {
  const { models } = normalizeCatalog(await readFixture())
  const glm = models.find((model) => model.id === "glm-5.3-flash")

  assert.deepEqual(glm.cost, { input: 0.15, output: 0.5, cacheRead: 0.03 })
})

test("normalizeCatalog records DeepSeek OFF-PEAK pricing as the neutral baseline", async () => {
  const { models } = normalizeCatalog(await readFixture())

  // The neutral schema has no time-of-day tiering. Off-peak is the lower,
  // baseline price: V4 Pro $0.66/$1.98/$0.022, V4.1 Flash $0.15/$0.60/$0.003.
  assert.deepEqual(models.find((model) => model.id === "deepseek-v4-pro").cost, {
    input: 0.66,
    output: 1.98,
    cacheRead: 0.022,
  })
  assert.deepEqual(models.find((model) => model.id === "deepseek-v4.1-flash").cost, {
    input: 0.15,
    output: 0.6,
    cacheRead: 0.003,
  })
})

test("normalizeCatalog omits cacheWrite where OpenCode Go publishes no cache-write price", async () => {
  const { models } = normalizeCatalog(await readFixture())

  assert.equal("cacheWrite" in models.find((model) => model.id === "glm-5.3-flash").cost, false)
  assert.equal("cacheWrite" in models.find((model) => model.id === "deepseek-v4-pro").cost, false)
  assert.equal(models.find((model) => model.id === "kimi-k3").cost.cacheWrite, 3)
})

test("normalizeCatalog keeps free models as explicit zero prices", async () => {
  const { models } = normalizeCatalog(await readFixture())
  const beam = models.find((model) => model.id === "beam-free")

  assert.deepEqual(beam.cost, { input: 0, output: 0, cacheRead: 0 })
})

test("normalizeCatalog copies only the four known cost keys", async () => {
  assert.deepEqual(
    normalizeCatalog({ data: [{ id: "beam-free", cost: { input: 0, unknown: "ignored" } }] }).models,
    [{ id: "beam-free", cost: { input: 0 } }],
  )
})

test("normalizeCatalog preserves recommendations that reference catalog ids", async () => {
  const neutral = normalizeCatalog(await readFixture())

  assert.deepEqual(neutral.recommendations, {
    primary: "deepseek-v4-pro",
    small: "glm-5.3-flash",
  })
})

test("normalizeCatalog rejects recommendations that reference an absent model", () => {
  assert.throws(
    () => normalizeCatalog({ data: [{ id: "glm-5.2" }], recommendations: { primary: "glm-5.3" } }),
    /recommendation 'primary' must reference a model id/,
  )
  assert.throws(
    () => normalizeCatalog({ data: [{ id: "glm-5.2" }], recommendations: { fastest: "glm-5.2" } }),
    /unsupported recommendation role 'fastest'/,
  )
})

test("normalizeCatalog rejects ids outside the OpenAI-compatible allowlist", () => {
  // These ids exist on the live models endpoint but are served over a different
  // protocol, are stealth/experimental, or are legacy. A raw /v1/models response
  // must fail rather than publish unroutable models.
  for (const id of ["gpt-6-luna", "gemini-4-argon", "space-bunny", "cat-jam-free", "glm-5.1"]) {
    assert.throws(
      () => normalizeCatalog({ data: [{ id }] }),
      /is not in the OpenAI-compatible allowlist/,
      `${id} should be rejected`,
    )
  }
})

test("normalizeCatalog throws a clear error when the source has no data[] array", () => {
  assert.throws(() => normalizeCatalog({ models: [] }), /missing a data\[\] array/)
  assert.throws(() => normalizeCatalog(null), /missing a data\[\] array/)
  assert.throws(() => normalizeCatalog({ object: "list" }), /missing a data\[\] array/)
})

test("normalizeCatalog rejects malformed model records with actionable errors", () => {
  const cases = [
    [[null], /data\[0\] must be an object \(got null\)/],
    [["gpt"], /data\[0\] must be an object \(got "gpt"\)/],
    [[{}], /data\[0\]\.id must be a non-empty string \(got undefined\)/],
    [[{ id: "" }], /data\[0\]\.id must be a non-empty string \(got ""\)/],
    [[{ id: "model\n" }], /not a valid neutral model identifier/],
    [[{ id: 123 }], /data\[0\]\.id must be a non-empty string \(got 123\)/],
    [[{ id: "model", contextWindow: -5 }], /data\[0\]\.contextWindow must be a positive integer/],
    [[{ id: "model", contextWindow: 1.5 }], /data\[0\]\.contextWindow must be a positive integer/],
    [[{ id: "model", contextWindow: Infinity }], /data\[0\]\.contextWindow must be a positive integer/],
    [[{ id: "model", contextWindow: null }], /data\[0\]\.contextWindow must be a positive integer/],
    [[{ id: "model", maxOutputTokens: 0 }], /data\[0\]\.maxOutputTokens must be a positive integer/],
    [[{ id: "model", maxOutputTokens: 2.5 }], /data\[0\]\.maxOutputTokens must be a positive integer/],
    [[{ id: "model", maxOutputTokens: "64000" }], /data\[0\]\.maxOutputTokens must be a positive integer/],
    [[{ id: "model", cost: null }], /data\[0\]\.cost must be an object \(got null\)/],
    [[{ id: "model", cost: "free" }], /data\[0\]\.cost must be an object \(got "free"\)/],
    [[{ id: "model", cost: [] }], /data\[0\]\.cost must be an object \(got \[\]\)/],
    [[{ id: "model", cost: { input: -1 } }], /data\[0\]\.cost\.input must be a non-negative finite number/],
    [[{ id: "model", cost: { output: Infinity } }], /data\[0\]\.cost\.output must be a non-negative finite number/],
  ]

  for (const [data, expected] of cases) {
    assert.throws(() => normalizeCatalog({ data }), expected)
  }
})

test("normalizeCatalog rejects duplicate and excessive model lists", () => {
  assert.throws(
    () => normalizeCatalog({ data: [{ id: "model-a" }, { id: "model-a" }] }),
    /duplicate model IDs/,
  )
  assert.throws(
    () => normalizeCatalog({ data: Array.from({ length: 501 }, (_, i) => ({ id: `model-${i}` })) }),
    /exceeds 500 entries/,
  )
})

test("normalizeCatalog accepts omitted optional metadata and an empty catalog", () => {
  assert.deepEqual(normalizeCatalog({ data: [{ id: "glm-5.2" }] }).models, [{ id: "glm-5.2" }])
  assert.deepEqual(normalizeCatalog({ data: [] }).models, [])
})

test("CLI: reads --source and writes --out, producing valid JSON matching normalizeCatalog", async () => {
  const { execFile } = await import("node:child_process")
  const { promisify } = await import("node:util")
  const execFileAsync = promisify(execFile)

  const scriptPath = path.join(__dirname, "../scripts/normalize-catalog.mjs")
  const outPath = path.join(__dirname, "output/normalize-catalog-cli-test.json")

  await execFileAsync(process.execPath, [scriptPath, "--source", fixturePath, "--out", outPath])

  const written = JSON.parse(await readFile(outPath, "utf8"))
  assert.deepEqual(written, normalizeCatalog(await readFixture()))

  await rm(path.dirname(outPath), { recursive: true, force: true })
})

test("CLI: rejects unknown options and missing option values", async () => {
  const { execFile } = await import("node:child_process")
  const { promisify } = await import("node:util")
  const execFileAsync = promisify(execFile)
  const scriptPath = path.join(__dirname, "../scripts/normalize-catalog.mjs")

  await assert.rejects(execFileAsync(process.execPath, [scriptPath, "--soruce", fixturePath]), /unknown option/)
  await assert.rejects(execFileAsync(process.execPath, [scriptPath, "--source"]), /requires a path/)
  await assert.rejects(execFileAsync(process.execPath, [scriptPath, "--out"]), /requires a path/)
})

test("CLI: still runs when invoked through a symlink/junction to the kit", async (t) => {
  // Node resolves a module's realpath for import.meta.url but leaves
  // process.argv[1] as the link path. A naive string comparison therefore
  // silently no-ops. This invokes the script through a linked kit directory and
  // asserts real output, which fails if entry-point detection regresses.
  const { execFile } = await import("node:child_process")
  const { promisify } = await import("node:util")
  const os = await import("node:os")
  const { mkdtemp, symlink, rm } = await import("node:fs/promises")
  const execFileAsync = promisify(execFile)

  const kitRoot = path.resolve(__dirname, "..")
  const tmpDir = await mkdtemp(path.join(os.tmpdir(), "opencode-go-kit-link-"))
  const linkPath = path.join(tmpDir, "kit-link")
  const outPath = path.join(tmpDir, "linked-output.json")

  try {
    try {
      // A Windows junction needs no elevation; a POSIX symlink is equivalent.
      await symlink(kitRoot, linkPath, process.platform === "win32" ? "junction" : "dir")
    } catch (error) {
      t.skip(`cannot create a directory symlink here (${error.code}); CI covers this on Linux`)
      return
    }

    const linkedScript = path.join(linkPath, "scripts/normalize-catalog.mjs")
    await execFileAsync(process.execPath, [linkedScript, "--source", fixturePath, "--out", outPath])

    const written = JSON.parse(await readFile(outPath, "utf8"))
    assert.equal(written.models.length, OPENAI_COMPATIBLE_MODEL_IDS.length)
    assert.deepEqual(written, normalizeCatalog(await readFixture()))
  } finally {
    await rm(tmpDir, { recursive: true, force: true })
  }
})

// ---------------------------------------------------------------------------
// Drift gate for the SHIPPED snapshot.
//
// The snapshot must remain exactly equal to normalizer output, including
// recommendations, so the runtime projection cannot silently diverge from the
// authoring input.
// ---------------------------------------------------------------------------

test("shipped snapshot exactly matches normalizeCatalog(fixture)", async () => {
  const snapshot = JSON.parse(await readFile(snapshotPath, "utf8"))
  const regenerated = normalizeCatalog(await readFixture())

  // Guard the gate itself: if either side is empty the comparison below would
  // pass vacuously, which is the "no evidence read as a pass" defect.
  assert.ok(
    Array.isArray(snapshot.models) && snapshot.models.length > 0,
    "snapshot has no models[] -- nothing to compare, so this gate cannot pass",
  )
  assert.ok(
    Array.isArray(regenerated.models) && regenerated.models.length > 0,
    "normalizer produced no models[] from the fixture -- gate cannot pass",
  )

  assert.equal(snapshot.models.length, 18)
  assert.deepEqual(snapshot, regenerated)
})

test("shipped snapshot: envelope matches the normalizer and carries no credential or routing fields", async () => {
  const snapshot = JSON.parse(await readFile(snapshotPath, "utf8"))

  assert.equal(snapshot.schemaVersion, "acq-neutral-model-catalog/v1")
  assert.equal(snapshot.providerId, "opencode-go")

  // The snapshot ships to an AGENT-OWNED path (/home/agent/...), so it must
  // carry model metadata only. A routing or credential field here would let a
  // rewritten snapshot redirect a consumer.
  const forbidden = ["host", "baseUrl", "modelsUrl", "keyEnv", "apiKey", "apiProtocol"]
  for (const key of forbidden) {
    assert.ok(!(key in snapshot), `snapshot must not carry the routing/credential field '${key}'`)
    for (const model of snapshot.models) {
      assert.ok(!(key in model), `snapshot model '${model.id}' must not carry '${key}'`)
    }
  }
})

test("shipped snapshot: every model has display metadata and a complete base price", async () => {
  const snapshot = JSON.parse(await readFile(snapshotPath, "utf8"))

  for (const model of snapshot.models) {
    assert.equal(typeof model.name, "string", `${model.id} needs a name`)
    assert.ok(Number.isInteger(model.contextWindow) && model.contextWindow > 0, `${model.id} needs contextWindow`)
    assert.ok(Number.isInteger(model.maxOutputTokens) && model.maxOutputTokens > 0, `${model.id} needs maxOutputTokens`)
    assert.ok(model.cost, `${model.id} needs cost`)
    for (const key of ["input", "output", "cacheRead"]) {
      assert.equal(typeof model.cost[key], "number", `${model.id} needs cost.${key}`)
      assert.ok(model.cost[key] >= 0, `${model.id} cost.${key} must be non-negative`)
    }
  }
})
