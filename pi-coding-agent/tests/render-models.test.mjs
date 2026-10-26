import test from "node:test"
import assert from "node:assert/strict"
import { execFile } from "node:child_process"
import { lstat, mkdir, mkdtemp, readFile, rm, stat, symlink, unlink, writeFile } from "node:fs/promises"
import { promisify } from "node:util"
import os from "node:os"
import path from "node:path"
import { fileURLToPath } from "node:url"

import Ajv2020 from "ajv/dist/2020.js"
import { parse as parseYaml } from "yaml"

import { applyModelsProjection, CATALOG_FIELDS, COST_FIELDS, FACTS_FIELDS, loadProviderInputs, MODEL_FIELDS, renderModels } from "../files/home/pi-coding-agent-render-models.mjs"

const execFileAsync = promisify(execFile)
const KIT_ROOT = fileURLToPath(new URL("..", import.meta.url))
const RENDERER = path.join(KIT_ROOT, "files", "home", "pi-coding-agent-render-models.mjs")
const FIXTURES = path.join(KIT_ROOT, "tests", "fixtures", "opencode-go")

let piValidatorPromise

async function assertPiSchemaValid(document, label = "models.json") {
  piValidatorPromise ??= (async () => {
    const schema = await readJson(KIT_ROOT, "tests", "schemas", "pi-models.schema.json")
    const ajv = new Ajv2020({ allErrors: true, strict: false })
    return { validate: ajv.compile(schema), ajv }
  })()
  const { validate, ajv } = await piValidatorPromise
  assert.equal(validate(document), true, `${label}: ${ajv.errorsText(validate.errors)}`)
}

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
    await assertPiSchemaValid(document)
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

test("a model-less provider renders models: [] instead of failing", async () => {
  const directory = await tempDir()
  try {
    const catalog = {
      schemaVersion: "acq-neutral-model-catalog/v1",
      providerId: "opencode-go",
      models: [],
    }
    const document = await renderedFor(directory, { catalog })
    assert.deepEqual(document.providers["opencode-go"].models, [])
    await assertPiSchemaValid(document, "empty catalog")
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})

test("unknown facts or catalog fields fail closed like acq's schemas do", async () => {
  const directory = await tempDir()
  try {
    const facts = await fixtureFacts()
    const catalog = await fixtureCatalog()
    await assert.rejects(
      renderedFor(path.join(directory, "facts"), { facts: { ...facts, extra: true } }),
      /facts for 'opencode-go' contains unsupported field 'extra'/,
    )
    await assert.rejects(
      renderedFor(path.join(directory, "catalog"), { catalog: { ...catalog, extra: true } }),
      /snapshot for 'opencode-go' contains unsupported field 'extra'/,
    )
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

    for (const prototypeKey of ["__proto__", "constructor", "toString"]) {
      await assert.rejects(
        renderedFor(path.join(directory, prototypeKey.replaceAll("_", "x")), {
          facts: { ...facts, apiProtocol: prototypeKey },
          catalog,
        }),
        /unsupported apiProtocol/,
      )
    }
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

test("host agreement is case-insensitive, rejects trailing dots, and handles punycode", async () => {
  const directory = await tempDir()
  try {
    const facts = await fixtureFacts()
    const catalog = { ...(await fixtureCatalog()), models: [], recommendations: {} }

    const upper = await renderedFor(path.join(directory, "upper"), { facts: { ...facts, host: "OPENCODE.AI" }, catalog })
    assert.equal(upper.providers["opencode-go"].baseUrl, "https://opencode.ai/inference/go/openai/v1")

    await assert.rejects(
      renderedFor(path.join(directory, "trailing-dot"), { facts: { ...facts, host: "opencode.ai." }, catalog }),
      /invalid host/,
    )

    const punycode = await renderedFor(path.join(directory, "punycode"), {
      facts: {
        ...facts,
        host: "xn--bcher-kva.example",
        baseUrl: "https://bücher.example/v1",
        modelsUrl: "https://bücher.example/v1/models",
      },
      catalog,
    })
    assert.equal(punycode.providers["opencode-go"].baseUrl, "https://bücher.example/v1")
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
    const minimal = {
      schemaVersion: "acq-neutral-model-catalog/v1",
      providerId: "opencode-go",
      models: [{ id: "model-a" }, { id: "model-b", cost: { input: 1 } }],
    }
    const document = await renderedFor(directory, { catalog: minimal })
    assert.deepEqual(document.providers["opencode-go"].models[0], { id: "model-a", name: "model-a" })
    assert.equal("contextWindow" in document.providers["opencode-go"].models[0], false)
    assert.equal("maxTokens" in document.providers["opencode-go"].models[0], false)
    assert.deepEqual(document.providers["opencode-go"].models[1], {
      id: "model-b",
      name: "model-b",
      cost: { input: 1, output: 0, cacheRead: 0, cacheWrite: 0 },
    })
    await assertPiSchemaValid(document, "partial cost")

    const fullCost = {
      ...minimal,
      models: [{
        id: "model-c",
        name: "Model C",
        contextWindow: 128000,
        maxOutputTokens: 8192,
        cost: { input: 1, output: 2, cacheRead: 0.1, cacheWrite: 0.2 },
      }],
    }
    const fullDocument = await renderedFor(path.join(directory, "full"), { catalog: fullCost })
    assert.deepEqual(fullDocument.providers["opencode-go"].models[0], {
      id: "model-c",
      name: "Model C",
      contextWindow: 128000,
      maxTokens: 8192,
      cost: { input: 1, output: 2, cacheRead: 0.1, cacheWrite: 0.2 },
    })
    await assertPiSchemaValid(fullDocument, "full cost")

    const unknownCost = { ...minimal, models: [{ id: "model-a", cost: { cache_write: 1 } }] }
    await assert.rejects(
      renderedFor(path.join(directory, "unknown-cost"), { catalog: unknownCost }),
      /unsupported field 'cache_write'/,
    )
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})

test("neutral tiered pricing maps to a valid pi cost tier, with or without base cost", async () => {
  const directory = await tempDir()
  try {
    const withBase = {
      schemaVersion: "acq-neutral-model-catalog/v1",
      providerId: "opencode-go",
      models: [{
        id: "tiered",
        contextWindow: 1000000,
        cost: { input: 1, output: 2, cacheRead: 0.1, cacheWrite: 0 },
        costAbove200kContext: { input: 3, output: 4, cacheRead: 0.2, cacheWrite: 0.3 },
      }],
    }
    const withBaseDocument = await renderedFor(path.join(directory, "with-base"), { catalog: withBase })
    assert.deepEqual(withBaseDocument.providers["opencode-go"].models[0].cost, {
      input: 1,
      output: 2,
      cacheRead: 0.1,
      cacheWrite: 0,
      tiers: [{ inputTokensAbove: 200000, input: 3, output: 4, cacheRead: 0.2, cacheWrite: 0.3 }],
    })
    await assertPiSchemaValid(withBaseDocument, "tiered cost with base")

    const tierOnly = {
      schemaVersion: "acq-neutral-model-catalog/v1",
      providerId: "opencode-go",
      models: [{ id: "tier-only", costAbove200kContext: { input: 3, output: 4 } }],
    }
    const tierOnlyDocument = await renderedFor(path.join(directory, "tier-only"), { catalog: tierOnly })
    assert.deepEqual(tierOnlyDocument.providers["opencode-go"].models[0].cost, {
      input: 0,
      output: 0,
      cacheRead: 0,
      cacheWrite: 0,
      tiers: [{ inputTokensAbove: 200000, input: 3, output: 4, cacheRead: 0, cacheWrite: 0 }],
    })
    await assertPiSchemaValid(tierOnlyDocument, "tiered cost without base")
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})

test("duplicate provider inputs, more than 500 models, and bad recommendations fail closed", async () => {
  const directory = await tempDir()
  try {
    const facts = await fixtureFacts()
    const catalog = await fixtureCatalog()

    const input = { directory: "opencode-go", facts, catalog }
    assert.throws(() => renderModels([input, input]), /duplicate provider 'opencode-go'/)

    const tooMany = {
      schemaVersion: "acq-neutral-model-catalog/v1",
      providerId: "opencode-go",
      models: Array.from({ length: 501 }, (_, index) => ({ id: `model-${index}` })),
    }
    await assert.rejects(
      renderedFor(path.join(directory, "too-many"), { catalog: tooMany }),
      /exceeds the neutral catalog limit/,
    )

    const validRecommendations = { ...catalog, recommendations: { primary: "glm-5.3-flash", small: "glm-5.3", compaction: "hy3", summary: "hy3", title: "hy3" } }
    const validDocument = await renderedFor(path.join(directory, "valid-recommendations"), { catalog: validRecommendations })
    await assertPiSchemaValid(validDocument, "valid recommendations")

    await assert.rejects(
      renderedFor(path.join(directory, "unknown-role"), { catalog: { ...catalog, recommendations: { reasoning: "hy3" } } }),
      /unsupported recommendation role/,
    )
    await assert.rejects(
      renderedFor(path.join(directory, "dangling"), { catalog: { ...catalog, recommendations: { primary: "missing-model" } } }),
      /dangling primary recommendation/,
    )
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})

test("schema full-match semantics reject trailing newlines and control characters", async () => {
  const directory = await tempDir()
  try {
    const facts = await fixtureFacts()
    const catalog = await fixtureCatalog()

    await assert.rejects(
      renderedFor(path.join(directory, "provider-id"), {
        facts: { ...facts, providerId: "opencode-go\n" },
        catalog: { ...catalog, providerId: "opencode-go\n" },
      }),
      /invalid providerId/,
    )
    await assert.rejects(
      renderedFor(path.join(directory, "key-env"), { facts: { ...facts, keyEnv: "OPENCODE_GO_API_KEY\n" } }),
      /invalid keyEnv/,
    )
    await assert.rejects(
      renderedFor(path.join(directory, "host"), {
        facts: { ...facts, host: "opencode.ai\n", baseUrl: "https://opencode.ai/v1", modelsUrl: "https://opencode.ai/v1/models" },
      }),
      /invalid host/,
    )

    const controlId = { ...catalog, models: [{ id: "model-a\u0000" }] }
    await assert.rejects(
      renderedFor(path.join(directory, "control-id"), { catalog: controlId }),
      /disallowed control characters/,
    )
    const controlName = { ...catalog, models: [{ id: "model-a", name: "bad\nname" }] }
    await assert.rejects(
      renderedFor(path.join(directory, "control-name"), { catalog: controlName }),
      /disallowed control characters/,
    )
    const longId = { ...catalog, models: [{ id: "x".repeat(129) }] }
    await assert.rejects(
      renderedFor(path.join(directory, "long-id"), { catalog: longId }),
      /exceeds 128 characters/,
    )
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})

test("numeric and cost validation matches the neutral schema", async () => {
  const directory = await tempDir()
  try {
    const reject = async (name, model, pattern) => {
      const catalog = {
        schemaVersion: "acq-neutral-model-catalog/v1",
        providerId: "opencode-go",
        models: [model],
      }
      await assert.rejects(
        renderedFor(path.join(directory, name), { catalog }),
        pattern,
      )
    }

    await reject("zero-context", { id: "model-a", contextWindow: 0 }, /positive integer/)
    await reject("fractional-context", { id: "model-a", contextWindow: 1.5 }, /positive integer/)
    await reject("zero-output", { id: "model-a", maxOutputTokens: 0 }, /positive integer/)
    await reject("negative-cost", { id: "model-a", cost: { input: -1 } }, /non-negative number/)
    await reject("string-cost", { id: "model-a", cost: { input: "1" } }, /non-negative number/)

    const notArray = {
      schemaVersion: "acq-neutral-model-catalog/v1",
      providerId: "opencode-go",
      models: {},
    }
    await assert.rejects(
      renderedFor(path.join(directory, "not-array"), { catalog: notArray }),
      /must be an array/,
    )

    const uppercaseProtocolUrl = {
      schemaVersion: "acq-neutral-model-catalog/v1",
      providerId: "opencode-go",
      models: [],
    }
    const facts = await fixtureFacts()
    await assert.rejects(
      renderedFor(path.join(directory, "uppercase-url"), {
        facts: { ...facts, baseUrl: "HTTPS://opencode.ai/v1" },
        catalog: uppercaseProtocolUrl,
      }),
      /must start with https:\/\//,
    )
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})

test("atomic write replaces a symlink at the target instead of following it", { skip: process.platform === "win32" }, async () => {
  const directory = await tempDir()
  try {
    const root = await makeRoot(directory)
    const victim = path.join(directory, "victim.json")
    const modelsFile = path.join(directory, "models.json")
    await writeFile(victim, "sentinel\n")
    await symlink(victim, modelsFile)

    assert.equal(await applyModelsProjection(root, modelsFile), "authoritative")

    assert.equal(await readFile(victim, "utf8"), "sentinel\n")
    assert.equal((await lstat(modelsFile)).isSymbolicLink(), false)
    await assertPiSchemaValid(JSON.parse(await readFile(modelsFile, "utf8")), "symlink target replacement")
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})

test("symlinked provider directories and input files are rejected", { skip: process.platform === "win32" }, async () => {
  const directory = await tempDir()
  try {
    const facts = await fixtureFacts()
    const catalog = await fixtureCatalog()

    const root = path.join(directory, "provider-input")
    const providers = path.join(root, "models", "providers")
    const outside = path.join(directory, "outside")
    await mkdir(providers, { recursive: true })
    await mkdir(outside, { recursive: true })
    await writeFile(path.join(outside, "facts.json"), JSON.stringify(facts))
    await writeFile(path.join(outside, "snapshot.json"), JSON.stringify(catalog))
    await symlink(outside, path.join(providers, "opencode-go"), "dir")
    await assert.rejects(loadProviderInputs(root), /provider directory 'opencode-go' must not be a symlink/)

    await unlink(path.join(providers, "opencode-go"))
    const providerDir = path.join(providers, "opencode-go")
    await mkdir(providerDir, { recursive: true })
    await symlink(path.join(outside, "facts.json"), path.join(providerDir, "facts.json"))
    await writeFile(path.join(providerDir, "snapshot.json"), JSON.stringify(catalog))
    await assert.rejects(loadProviderInputs(root), /facts for 'opencode-go' must not be a symlink/)
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

test("renderer field allowlists match the vendored neutral schemas", async () => {
  const factsSchema = await readJson(KIT_ROOT, "tests", "schemas", "acq-provider-facts.schema.json")
  const catalogSchema = await readJson(KIT_ROOT, "tests", "schemas", "acq-neutral-model-catalog.schema.json")

  assert.deepEqual([...FACTS_FIELDS].sort(), Object.keys(factsSchema.properties).sort())
  assert.deepEqual([...CATALOG_FIELDS].sort(), Object.keys(catalogSchema.properties).sort())
  assert.deepEqual([...MODEL_FIELDS].sort(), Object.keys(catalogSchema.$defs.model.properties).sort())
  assert.deepEqual([...COST_FIELDS].sort(), Object.keys(catalogSchema.$defs.cost.properties).sort())
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

test("CLI defaults to ACQ_PROVIDER_INPUT_ROOT and $HOME/.pi/agent/models.json", async () => {
  const directory = await tempDir()
  try {
    const root = await makeRoot(directory)
    const home = path.join(directory, "home")
    const env = { ...process.env, HOME: home, ACQ_PROVIDER_INPUT_ROOT: root }
    delete env.PI_CODING_AGENT_DIR

    const result = await execFileAsync(process.execPath, [RENDERER], { env })
    assert.equal(result.stderr, "")
    const modelsFile = path.join(home, ".pi", "agent", "models.json")
    const document = JSON.parse(await readFile(modelsFile, "utf8"))
    await assertPiSchemaValid(document, "default path")
    assert.equal(document.providers["opencode-go"].models.length, 19)
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})

test("kit spec conforms to the patterns schema and its cross-field rules", async () => {
  const spec = parseYaml(await readFile(path.join(KIT_ROOT, "spec.yaml"), "utf8"))
  const schema = await readJson(KIT_ROOT, "tests", "schemas", "kit-hybrid-v1.schema.json")
  const ajv = new Ajv2020({ allErrors: true, strict: false })
  const validate = ajv.compile(schema)
  assert.equal(validate(spec), true, ajv.errorsText(validate.errors))

  assert.equal(spec.schemaVersion, "hybrid/v1")
  assert.equal(spec.kind, "mixin")
  assert.equal(spec.name, "pi-coding-agent")
  assert.equal(spec.name, path.basename(KIT_ROOT))
  assert.deepEqual(spec.caps.network.allow, ["registry.npmjs.org"])
  assert.equal("agent" in spec, false)
  assert.equal("publishedPorts" in spec, false)
  assert.equal(spec.files.length, 2)
  assert.deepEqual(spec.files.map((file) => file.path), [
    "/home/agent/pi-coding-agent-install.sh",
    "/home/agent/pi-coding-agent-render-models.mjs",
  ])
  for (const file of spec.files) {
    assert.equal(file.mode, "0755")
    assert.match(file.path, /^\/[A-Za-z0-9._/-]+$/)
    assert.equal((await stat(path.join(KIT_ROOT, file.source))).isFile(), true)
  }
  assert.equal((await stat(path.join(KIT_ROOT, "README.md"))).isFile(), true)
  assert.deepEqual(spec.commands.map((command) => command.phase), ["startup", "startup"])
  assert.deepEqual(spec.commands.map((command) => command.command), [
    ["sh", "/home/agent/pi-coding-agent-install.sh"],
    ["node", "/home/agent/pi-coding-agent-render-models.mjs"],
  ])
  for (const command of spec.commands) assert.equal(command.user, "1000")
})
