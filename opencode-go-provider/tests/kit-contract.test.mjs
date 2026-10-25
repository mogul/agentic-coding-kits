import test from "node:test"
import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"

import Ajv2020 from "ajv/dist/2020.js"
import { parse as parseYaml } from "yaml"

import { OPENAI_COMPATIBLE_MODEL_IDS } from "../scripts/normalize-catalog.mjs"

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const KIT_ROOT = path.resolve(__dirname, "..")

async function readJson(...parts) {
  return JSON.parse(await readFile(path.join(KIT_ROOT, ...parts), "utf8"))
}

const bundle = await readJson("provider-input.json")
const facts = await readJson("provider-input", "facts.json")
const snapshot = await readJson("files", "home", "opencode-go", "model-catalog-snapshot.json")
const fixture = await readJson("tests", "fixtures", "normalize-source.json")
const spec = parseYaml(await readFile(path.join(KIT_ROOT, "spec.yaml"), "utf8"))

test("bundle and facts agree on providerId, paths, and credential names", () => {
  assert.equal(bundle.schemaVersion, "acq-provider-input-bundle/v2")
  assert.equal(facts.schemaVersion, "acq-provider-facts/v1")
  assert.equal(bundle.providerId, facts.providerId)
  assert.equal(bundle.providerId, "opencode-go")

  assert.equal(bundle.factsPath, "provider-input/facts.json")
  assert.equal(bundle.normalizerPath, "scripts/normalize-catalog.mjs")
  assert.equal(bundle.snapshotPath, "files/home/opencode-go/model-catalog-snapshot.json")
  assert.equal(bundle.providerPath, `models/providers/${facts.providerId}`)

  assert.deepEqual(bundle.credentialEnvNames, [facts.keyEnv])
  assert.equal(facts.keyEnv, "OPENCODE_GO_API_KEY")

  // The credential list carries NAMES, never values: an env-var name is
  // uppercase letters, digits, and underscores, and looks nothing like a key.
  for (const name of bundle.credentialEnvNames) {
    assert.match(name, /^[A-Z][A-Z0-9_]*$/)
  }
})

test("facts URLs share the declared host and use HTTPS", () => {
  assert.equal(facts.apiProtocol, "openai-compatible")

  for (const url of [facts.baseUrl, facts.modelsUrl]) {
    const parsed = new URL(url)
    assert.equal(parsed.protocol, "https:")
    assert.equal(parsed.hostname, facts.host)
    assert.equal(parsed.port, "")
    assert.equal(parsed.username, "")
    assert.equal(parsed.password, "")
    assert.equal(parsed.hash, "")
  }

  assert.equal(facts.baseUrl, "https://opencode.ai/inference/go/openai/v1")
  assert.equal(facts.modelsUrl, "https://opencode.ai/inference/go/v1/models")
})

test("spec allow-lists facts.host and drops the declared snapshot", () => {
  assert.equal(spec.schemaVersion, "hybrid/v1")
  assert.equal(spec.kind, "mixin")
  assert.equal(spec.name, "opencode-go-provider")

  assert.deepEqual(spec.caps.network.allow, [facts.host])

  assert.ok(Array.isArray(spec.files), "spec.files must be an array")
  assert.equal(spec.files.length, 1)
  assert.deepEqual(spec.files[0], {
    path: "/home/agent/opencode-go/model-catalog-snapshot.json",
    mode: "0644",
    source: bundle.snapshotPath,
  })

  assert.deepEqual(spec.backend_shortcuts, { sbx: {}, msb: {} })
})

test("spec declares no environment block (injected credentials own that channel)", () => {
  // Deliberate: an empty OPENCODE_GO_API_KEY here could shadow the placeholder
  // the backend injects. The patterns env-ownership check is aspirational today,
  // and the kit needs no environment variables of its own.
  assert.equal("environment" in spec, false)
})

test("spec agentContext states the routing, region, and session preconditions", () => {
  assert.match(spec.agentContext, /OPENCODE_GO_API_KEY/)
  assert.match(spec.agentContext, /openai-compatible/i)
  assert.match(spec.agentContext, /x-opencode-session/)
  assert.match(spec.agentContext, /Global/)
  assert.match(spec.agentContext, /user-agent/i)
})

test("snapshot conforms to the vendored acq-neutral-model-catalog schema", async () => {
  const schema = await readJson("tests", "schemas", "acq-neutral-model-catalog.schema.json")
  const ajv = new Ajv2020({ allErrors: true, strict: false })
  const validate = ajv.compile(schema)

  const valid = validate(snapshot)
  assert.equal(valid, true, ajv.errorsText(validate.errors))

  assert.equal(snapshot.providerId, facts.providerId)
  assert.equal(snapshot.schemaVersion, "acq-neutral-model-catalog/v1")
})

test("allowlist, fixture, and snapshot describe the same protocol set", () => {
  assert.deepEqual(
    fixture.data.map((model) => model.id),
    OPENAI_COMPATIBLE_MODEL_IDS,
  )
  assert.deepEqual(
    snapshot.models.map((model) => model.id),
    OPENAI_COMPATIBLE_MODEL_IDS,
  )

  for (const role of ["primary", "small"]) {
    assert.ok(
      OPENAI_COMPATIBLE_MODEL_IDS.includes(snapshot.recommendations[role]),
      `recommendations.${role} must be an OpenAI-compatible model`,
    )
  }
})
