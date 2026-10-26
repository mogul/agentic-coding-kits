import test from "node:test"
import assert from "node:assert/strict"
import { execFile } from "node:child_process"
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises"
import { promisify } from "node:util"
import os from "node:os"
import path from "node:path"
import { fileURLToPath } from "node:url"

import Ajv2020 from "ajv/dist/2020.js"
import { parse as parseYaml } from "yaml"

import { applyModelsProjection, loadProviderInputs, renderModels } from "../files/home/pi-coding-agent-render-models.mjs"

const execFileAsync = promisify(execFile)
const KIT_ROOT = fileURLToPath(new URL("..", import.meta.url))
const RENDERER = path.join(KIT_ROOT, "files", "home", "pi-coding-agent-render-models.mjs")
const FIXTURES = path.join(KIT_ROOT, "tests", "fixtures", "opencode-go")

async function readJson(...parts) {
  return JSON.parse(await readFile(path.join(...parts), "utf8"))
}

async function fixtureFacts() {
  return readJson(FIXTURES, "facts.json")
}

async function fixtureCatalog() {
  return readJson(FIXTURES, "snapshot.json")
}

async function tempDir() {
  return mkdtemp(path.join(os.tmpdir(), "pi-coding-agent-test-"))
}

/**
 * Build a provider-generation layout:
 *   <tmp>/provider-input/models/providers/<providerId>/facts.json
 *   <tmp>/provider-input/models/providers/<providerId>/snapshot.json
 */
async function makeRoot(directory, options = {}) {
  const providerId = options.providerId ?? "opencode-go"
  const facts = options.facts ?? await fixtureFacts()
  const catalog = options.catalog ?? await fixtureCatalog()
  const providerDir = path.join(directory, "provider-input", "models", "providers", providerId)
  await mkdir(providerDir, { recursive: true })
  await writeFile(path.join(providerDir, "facts.json"), JSON.stringify(facts))
  await writeFile(path.join(providerDir, "snapshot.json"), JSON.stringify(catalog))
  return path.join(directory, "provider-input")
}

async function renderedFor(directory, options = {}) {
  const root = await makeRoot(directory, options)
  return renderModels(await loadProviderInputs(root))
}

test("happy path: opencode-go facts and catalog render the exact pi models.json shape", async () => {
  const directory = await tempDir()
  try {
    const root = await makeRoot(directory)
    const modelsFile = path.join(directory, "home", ".pi", "agent", "models.json")

    assert.equal(await applyModelsProjection(root, modelsFile), "authoritative")

    const document = JSON.parse(await readFile(modelsFile, "utf8"))
    assert.deepEqual(Object.keys(document), ["$schema", "providers"])
    assert.equal(document.$schema, "https://pi.dev/schemas/models.schema.json")

    const provider = document.providers["opencode-go"]
    assert.equal(provider.baseUrl, "https://opencode.ai/inference/go/openai/v1")
    assert.equal(provider.api, "openai-completions")
    assert.equal(provider.apiKey, "$OPENCODE_GO_API_KEY")
    assert.equal(provider.authHeader, true)

    const catalog = await fixtureCatalog()
    assert.equal(provider.models.length, 19)
    assert.deepEqual(
      provider.models.map((model) => model.id),
      catalog.models.map((model) => model.id),
    )

    // Exact first-model mapping, including cacheWrite defaulted to 0 because
    // pi's ModelCost requires all four fields.
    assert.deepEqual(provider.models[0], {
      id: "glm-5.3-flash",
      name: "GLM-5.3-Flash",
      contextWindow: 1000000,
      maxTokens: 131072,
      cost: { input: 0.15, output: 0.5, cacheRead: 0.03, cacheWrite: 0 },
    })
    assert.deepEqual(provider.models.find((model) => model.id === "kimi-k3.1-pro").cost, {
      input: 2,
      output: 10,
      cacheRead: 0.2,
      cacheWrite: 2,
    })

    for (const model of provider.models) {
      assert.deepEqual(Object.keys(model.cost).sort(), ["cacheRead", "cacheWrite", "input", "output"])
    }
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})

test("missing provider root is not-ready and leaves existing models.json untouched", async () => {
  const directory = await tempDir()
  try {
    const modelsFile = path.join(directory, "models.json")
    await writeFile(modelsFile, '{"sentinel":true}\n')

    assert.equal(await applyModelsProjection(path.join(directory, "absent"), modelsFile), "not-ready")
    assert.equal(await readFile(modelsFile, "utf8"), '{"sentinel":true}\n')
    assert.equal(await loadProviderInputs(path.join(directory, "absent")), null)
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})

test("malformed facts or catalog fails closed without writing", async () => {
  const directory = await tempDir()
  try {
    const modelsFile = path.join(directory, "models.json")
    await writeFile(modelsFile, '{"sentinel":true}\n')
    const facts = await fixtureFacts()
    const catalog = await fixtureCatalog()

    const badFactsRoot = await makeRoot(path.join(directory, "bad-facts"), {
      facts: { ...facts, schemaVersion: "acq-provider-facts/v2" },
    })
    await assert.rejects(applyModelsProjection(badFactsRoot, modelsFile), /unsupported facts schema/)

    const badCatalogRoot = await makeRoot(path.join(directory, "bad-catalog"), {
      catalog: { ...catalog, schemaVersion: "acq-neutral-model-catalog/v2" },
    })
    await assert.rejects(applyModelsProjection(badCatalogRoot, modelsFile), /unsupported catalog schema/)

    assert.equal(await readFile(modelsFile, "utf8"), '{"sentinel":true}\n')
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})

test("provider identity must agree across directory, facts, and catalog", async () => {
  const directory = await tempDir()
  try {
    const facts = await fixtureFacts()
    const catalog = await fixtureCatalog()

    const catalogMismatch = await makeRoot(path.join(directory, "catalog-mismatch"), {
      catalog: { ...catalog, providerId: "other-provider" },
    })
    const catalogMismatchInputs = await loadProviderInputs(catalogMismatch)
    assert.throws(() => renderModels(catalogMismatchInputs), /catalog providerId does not match/)

    const factsMismatch = await makeRoot(path.join(directory, "facts-mismatch"), {
      facts: { ...facts, providerId: "other-provider" },
      catalog: { ...catalog, providerId: "other-provider" },
    })
    const factsMismatchInputs = await loadProviderInputs(factsMismatch)
    assert.throws(() => renderModels(factsMismatchInputs), /does not match directory 'opencode-go'/)
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})

test("unsupported apiProtocol fails closed", async () => {
  const directory = await tempDir()
  try {
    const facts = await fixtureFacts()
    const catalog = await fixtureCatalog()
    const root = await makeRoot(directory, { facts: { ...facts, apiProtocol: "anthropic-messages" } })
    const inputs = await loadProviderInputs(root)
    assert.throws(() => renderModels(inputs), /unsupported apiProtocol/)
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})

test("host/baseUrl/modelsUrl mismatches fail closed", async () => {
  const directory = await tempDir()
  try {
    const facts = await fixtureFacts()
    const catalog = await fixtureCatalog()

    await assert.rejects(
      renderedFor(path.join(directory, "base"), { facts: { ...facts, baseUrl: "https://evil.example.test/v1" } }),
      /baseUrl host does not match/,
    )
    await assert.rejects(
      renderedFor(path.join(directory, "models"), { facts: { ...facts, modelsUrl: "https://evil.example.test/v1/models" } }),
      /modelsUrl host does not match/,
    )
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})

test("invalid provider ids, key names, and duplicate model ids fail closed", async () => {
  const directory = await tempDir()
  try {
    const facts = await fixtureFacts()
    const catalog = await fixtureCatalog()

    await assert.rejects(
      makeRoot(path.join(directory, "bad-dir"), { providerId: "Not-A-Provider", facts: { ...facts, providerId: "Not-A-Provider" }, catalog: { ...catalog, providerId: "Not-A-Provider" } })
        .then((root) => loadProviderInputs(root)),
      /invalid provider directory/,
    )

    await assert.rejects(
      renderedFor(path.join(directory, "bad-key"), { facts: { ...facts, keyEnv: "not-a-key" } }),
      /invalid keyEnv/,
    )

    const duplicate = { ...catalog, models: [...catalog.models, { ...catalog.models[0] }] }
    await assert.rejects(
      renderedFor(path.join(directory, "duplicate"), { catalog: duplicate }),
      /duplicate model/,
    )
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})

test("defaults: name falls back to id, missing cost fields become 0, and unknown cost fields fail", async () => {
  const directory = await tempDir()
  try {
    const facts = await fixtureFacts()
    const minimal = {
      schemaVersion: "acq-neutral-model-catalog/v1",
      providerId: "opencode-go",
      models: [{ id: "model-a" }, { id: "model-b", cost: { input: 1 } }],
    }
    const document = await renderedFor(directory, { catalog: minimal })
    assert.deepEqual(document.providers["opencode-go"].models[0], { id: "model-a", name: "model-a" })
    assert.deepEqual(document.providers["opencode-go"].models[1], {
      id: "model-b",
      name: "model-b",
      cost: { input: 1, output: 0, cacheRead: 0, cacheWrite: 0 },
    })

    const unknownCost = { ...minimal, models: [{ id: "model-a", cost: { cache_write: 1 } }] }
    await assert.rejects(
      renderedFor(path.join(directory, "unknown-cost"), { catalog: unknownCost }),
      /unsupported field 'cache_write'/,
    )
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})

test("neutral tiered pricing maps to a pi cost tier", async () => {
  const directory = await tempDir()
  try {
    const catalog = {
      schemaVersion: "acq-neutral-model-catalog/v1",
      providerId: "opencode-go",
      models: [{
        id: "tiered",
        contextWindow: 1000000,
        cost: { input: 1, output: 2, cacheRead: 0.1, cacheWrite: 0 },
        costAbove200kContext: { input: 3, output: 4, cacheRead: 0.2, cacheWrite: 0.3 },
      }],
    }
    const document = await renderedFor(directory, { catalog })
    assert.deepEqual(document.providers["opencode-go"].models[0].cost, {
      input: 1,
      output: 2,
      cacheRead: 0.1,
      cacheWrite: 0,
      tiers: [{ inputTokensAbove: 200000, input: 3, output: 4, cacheRead: 0.2, cacheWrite: 0.3 }],
    })
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})

test("multiple providers render in deterministic provider-id order", async () => {
  const directory = await tempDir()
  try {
    const zetaFacts = { ...(await fixtureFacts()), providerId: "zeta-ai", host: "zeta.example.test", baseUrl: "https://zeta.example.test/v1", modelsUrl: "https://zeta.example.test/v1/models", keyEnv: "ZETA_AI_KEY" }
    const zetaCatalog = { ...(await fixtureCatalog()), providerId: "zeta-ai", models: [{ id: "z" }], recommendations: {} }
    // Both calls target the same <directory>/provider-input root.
    await makeRoot(directory)
    await makeRoot(directory, { providerId: "zeta-ai", facts: zetaFacts, catalog: zetaCatalog })

    const document = renderModels(await loadProviderInputs(path.join(directory, "provider-input")))
    assert.deepEqual(Object.keys(document.providers), ["opencode-go", "zeta-ai"])
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})

test("vendored schemas validate the opencode-go fixture", async () => {
  const facts = await fixtureFacts()
  const catalog = await fixtureCatalog()

  const factsSchema = await readJson(KIT_ROOT, "tests", "schemas", "acq-provider-facts.schema.json")
  const catalogSchema = await readJson(KIT_ROOT, "tests", "schemas", "acq-neutral-model-catalog.schema.json")
  const ajv = new Ajv2020({ allErrors: true, strict: false })

  const validateFacts = ajv.compile(factsSchema)
  assert.equal(validateFacts(facts), true, ajv.errorsText(validateFacts.errors))
  const validateCatalog = ajv.compile(catalogSchema)
  assert.equal(validateCatalog(catalog), true, ajv.errorsText(validateCatalog.errors))
})

test("CLI writes models.json, and a malformed generation exits non-zero", async () => {
  const directory = await tempDir()
  try {
    const root = await makeRoot(directory)
    const modelsFile = path.join(directory, "models.json")

    const ok = await execFileAsync(process.execPath, [RENDERER, "--provider-root", root, "--models-file", modelsFile])
    assert.equal(ok.stderr, "")
    const document = JSON.parse(await readFile(modelsFile, "utf8"))
    assert.equal(document.providers["opencode-go"].models.length, 19)

    const facts = await fixtureFacts()
    const badRoot = await makeRoot(path.join(directory, "bad"), { facts: { ...facts, apiProtocol: "unsupported" } })
    const sentinel = path.join(directory, "sentinel.json")
    await writeFile(sentinel, '{"sentinel":true}\n')

    await assert.rejects(
      execFileAsync(process.execPath, [RENDERER, "--provider-root", badRoot, "--models-file", sentinel]),
      (error) => {
        assert.equal(error.code, 1)
        assert.match(error.stderr, /unsupported apiProtocol/)
        return true
      },
    )
    assert.equal(await readFile(sentinel, "utf8"), '{"sentinel":true}\n')
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})

test("kit spec wires both startup commands and only the npm install host", async () => {
  const spec = parseYaml(await readFile(path.join(KIT_ROOT, "spec.yaml"), "utf8"))
  assert.equal(spec.schemaVersion, "hybrid/v1")
  assert.equal(spec.kind, "mixin")
  assert.equal(spec.name, "pi-coding-agent")
  assert.deepEqual(spec.caps.network.allow, ["registry.npmjs.org"])
  assert.equal("agent" in spec, false)
  assert.equal("publishedPorts" in spec, false)
  assert.equal(spec.files.length, 2)
  assert.deepEqual(spec.files.map((file) => file.path), [
    "/home/agent/pi-coding-agent-install.sh",
    "/home/agent/pi-coding-agent-render-models.mjs",
  ])
  for (const file of spec.files) assert.equal(file.mode, "0755")
  assert.deepEqual(spec.commands.map((command) => command.phase), ["startup", "startup"])
  assert.deepEqual(spec.commands.map((command) => command.command), [
    ["sh", "/home/agent/pi-coding-agent-install.sh"],
    ["node", "/home/agent/pi-coding-agent-render-models.mjs"],
  ])
  for (const command of spec.commands) assert.equal(command.user, "1000")
})
