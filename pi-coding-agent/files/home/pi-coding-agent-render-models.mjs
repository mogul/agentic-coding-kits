#!/usr/bin/env node
// Render acq's host-materialized provider generation into pi's models.json.
//
// acq mounts a read-only provider generation at $ACQ_PROVIDER_INPUT_ROOT:
//
//   models/providers/<providerId>/facts.json     (acq-provider-facts/v1)
//   models/providers/<providerId>/snapshot.json  (acq-neutral-model-catalog/v1)
//
// This renderer is the ONLY kit-owned writer of pi's provider configuration.
// It validates every input fail-closed and maps the neutral vocabulary onto
// pi's ~/.pi/agent/models.json schema:
//
//   facts.providerId          -> providers.<id>
//   facts.baseUrl             -> providers.<id>.baseUrl
//   openai-compatible         -> providers.<id>.api = "openai-completions"
//   facts.keyEnv              -> providers.<id>.apiKey = "$KEY_ENV"
//                                  (pi expands $NAME from the environment)
//   models[].id/name          -> models[].id/name
//   models[].contextWindow    -> models[].contextWindow
//   models[].maxOutputTokens  -> models[].maxTokens
//   models[].cost             -> models[].cost (all four fields required by pi)
//
// A missing provider root is NOT an empty provider set: it means the acq
// generation is not ready yet, so the existing models.json is left untouched.

import { mkdir, open, readdir, readFile, rename, rm } from "node:fs/promises"
import { randomBytes } from "node:crypto"
import path from "node:path"
import process from "node:process"
import { pathToFileURL } from "node:url"

const FACTS_SCHEMA = "acq-provider-facts/v1"
const CATALOG_SCHEMA = "acq-neutral-model-catalog/v1"
const MODELS_SCHEMA_URL = "https://pi.dev/schemas/models.schema.json"

// Mirrors acq-provider-facts.schema.json / acq-neutral-model-catalog.schema.json.
const PROVIDER_ID = /^[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?$/
const KEY_ENV = /^[A-Z][A-Z0-9_]*$/
const HOSTNAME = /^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)$/

// Harness-owned protocol adapters. The neutral protocol is a bounded value;
// adding one requires a deliberate renderer change, not a provider edit.
const API_PROTOCOLS = Object.freeze({
  "openai-compatible": "openai-completions",
})

const COST_FIELDS = Object.freeze(["input", "output", "cacheRead", "cacheWrite"])
const FACTS_FIELDS = new Set(["schemaVersion", "providerId", "apiProtocol", "host", "baseUrl", "modelsUrl", "keyEnv"])
const CATALOG_FIELDS = new Set(["schemaVersion", "providerId", "models", "recommendations"])
const MODEL_FIELDS = new Set(["id", "name", "contextWindow", "maxOutputTokens", "cost", "costAbove200kContext"])

function object(value, label) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object`)
  }
  return value
}

function string(value, label) {
  if (typeof value !== "string" || value.length === 0) throw new Error(`${label} must be a non-empty string`)
  return value
}

function positiveInteger(value, label) {
  if (!Number.isSafeInteger(value) || value < 1) throw new Error(`${label} must be a positive integer`)
  return value
}

function rejectUnknownFields(value, allowed, label) {
  for (const key of Object.keys(value)) {
    if (!allowed.has(key)) throw new Error(`${label} contains unsupported field '${key}'`)
  }
}

function httpsUrl(value, label) {
  let url
  try {
    url = new URL(string(value, label))
  } catch {
    throw new Error(`${label} must be a URL`)
  }
  if (url.protocol !== "https:" || !url.hostname || url.username || url.password || url.port || url.search || url.hash) {
    throw new Error(`${label} must be an HTTPS URL without credentials, port, query, or fragment`)
  }
  if (!HOSTNAME.test(url.hostname)) throw new Error(`${label} has an invalid hostname`)
  return url
}

function cost(value, label) {
  const source = object(value, label)
  rejectUnknownFields(source, new Set(COST_FIELDS), label)
  const result = {}
  for (const field of COST_FIELDS) {
    const amount = source[field] === undefined ? 0 : source[field]
    if (typeof amount !== "number" || !Number.isFinite(amount) || amount < 0) {
      throw new Error(`${label}.${field} must be a non-negative number`)
    }
    result[field] = amount
  }
  return result
}

function renderModel(model, providerId) {
  const source = object(model, `model for '${providerId}'`)
  rejectUnknownFields(source, MODEL_FIELDS, `model for '${providerId}'`)
  const id = string(source.id, `model id for '${providerId}'`)
  const reference = `${providerId}/${id}`
  const rendered = {
    id,
    name: source.name === undefined ? id : string(source.name, `model name for '${reference}'`),
  }
  if (source.contextWindow !== undefined) {
    rendered.contextWindow = positiveInteger(source.contextWindow, `context window for '${reference}'`)
  }
  if (source.maxOutputTokens !== undefined) {
    rendered.maxTokens = positiveInteger(source.maxOutputTokens, `output limit for '${reference}'`)
  }
  if (source.cost !== undefined) rendered.cost = cost(source.cost, `cost for '${reference}'`)
  if (source.costAbove200kContext !== undefined) {
    // pi expresses neutral tiered pricing as a request-wide tier. The neutral
    // schema's tier is fixed at "above 200k context".
    const tier = cost(source.costAbove200kContext, `tiered cost for '${reference}'`)
    rendered.cost = {
      ...(rendered.cost ?? { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 }),
      tiers: [{ inputTokensAbove: 200000, ...tier }],
    }
  }
  return [id, rendered]
}

function validateRecommendations(value, providerId, modelIds) {
  if (value === undefined) return
  const recommendations = object(value, `recommendations for '${providerId}'`)
  for (const [role, modelId] of Object.entries(recommendations)) {
    if (!["primary", "small", "compaction", "summary", "title"].includes(role)) {
      throw new Error(`unsupported recommendation role '${role}' for '${providerId}'`)
    }
    string(modelId, `${role} recommendation for '${providerId}'`)
    if (!modelIds.has(modelId)) {
      throw new Error(`dangling ${role} recommendation '${providerId}/${modelId}'`)
    }
  }
}

function renderProvider(input) {
  const facts = object(input.facts, `facts for '${input.directory}'`)
  const catalog = object(input.catalog, `snapshot for '${input.directory}'`)

  if (facts.schemaVersion !== FACTS_SCHEMA) throw new Error(`unsupported facts schema for '${input.directory}'`)
  if (catalog.schemaVersion !== CATALOG_SCHEMA) throw new Error(`unsupported catalog schema for '${input.directory}'`)
  rejectUnknownFields(facts, FACTS_FIELDS, `facts for '${input.directory}'`)
  rejectUnknownFields(catalog, CATALOG_FIELDS, `snapshot for '${input.directory}'`)

  const providerId = string(facts.providerId, `facts.providerId for '${input.directory}'`)
  if (!PROVIDER_ID.test(providerId)) throw new Error(`invalid providerId '${providerId}'`)
  if (providerId !== input.directory) {
    throw new Error(`facts providerId '${providerId}' does not match directory '${input.directory}'`)
  }
  if (string(catalog.providerId, `catalog.providerId for '${providerId}'`) !== providerId) {
    throw new Error(`catalog providerId does not match facts providerId '${providerId}'`)
  }

  const apiProtocol = string(facts.apiProtocol, `apiProtocol for '${providerId}'`)
  const piApi = API_PROTOCOLS[apiProtocol]
  if (piApi === undefined) throw new Error(`unsupported apiProtocol '${apiProtocol}' for '${providerId}'`)

  const host = string(facts.host, `host for '${providerId}'`).toLowerCase()
  if (!HOSTNAME.test(host)) throw new Error(`invalid host for '${providerId}'`)
  const baseUrl = string(facts.baseUrl, `baseUrl for '${providerId}'`)
  if (httpsUrl(baseUrl, `baseUrl for '${providerId}'`).hostname.toLowerCase() !== host) {
    throw new Error(`baseUrl host does not match '${providerId}'`)
  }
  const modelsUrl = string(facts.modelsUrl, `modelsUrl for '${providerId}'`)
  if (httpsUrl(modelsUrl, `modelsUrl for '${providerId}'`).hostname.toLowerCase() !== host) {
    throw new Error(`modelsUrl host does not match '${providerId}'`)
  }

  const keyEnv = string(facts.keyEnv, `keyEnv for '${providerId}'`)
  if (!KEY_ENV.test(keyEnv)) throw new Error(`invalid keyEnv for '${providerId}'`)

  if (!Array.isArray(catalog.models)) throw new Error(`models for '${providerId}' must be an array`)
  if (catalog.models.length > 500) throw new Error(`models for '${providerId}' exceeds the neutral catalog limit`)

  const models = []
  const modelIds = new Set()
  for (const model of catalog.models) {
    const [id, rendered] = renderModel(model, providerId)
    if (modelIds.has(id)) throw new Error(`duplicate model '${providerId}/${id}'`)
    modelIds.add(id)
    models.push(rendered)
  }
  validateRecommendations(catalog.recommendations, providerId, modelIds)

  return [providerId, {
    baseUrl,
    api: piApi,
    apiKey: `$${keyEnv}`,
    authHeader: true,
    models,
  }]
}

export function renderModels(inputs) {
  const providers = Object.create(null)
  const seen = new Set()
  for (const input of [...inputs].sort((left, right) => left.directory.localeCompare(right.directory))) {
    const [providerId, provider] = renderProvider(input)
    if (seen.has(providerId)) throw new Error(`duplicate provider '${providerId}'`)
    seen.add(providerId)
    providers[providerId] = provider
  }
  return { $schema: MODELS_SCHEMA_URL, providers }
}

export async function loadProviderInputs(providerRoot) {
  const current = path.join(providerRoot, "models", "providers")
  let entries
  try {
    entries = await readdir(current, { withFileTypes: true })
  } catch (error) {
    if (error?.code === "ENOENT") return null
    throw error
  }

  const inputs = []
  for (const entry of entries.sort((left, right) => left.name.localeCompare(right.name))) {
    if (entry.isSymbolicLink()) throw new Error(`provider directory '${entry.name}' must not be a symlink`)
    if (!entry.isDirectory()) continue
    if (!PROVIDER_ID.test(entry.name)) throw new Error(`invalid provider directory '${entry.name}'`)

    const directory = path.join(current, entry.name)
    const [factsText, catalogText] = await Promise.all([
      readFile(path.join(directory, "facts.json"), "utf8"),
      readFile(path.join(directory, "snapshot.json"), "utf8"),
    ])
    let facts
    let catalog
    try {
      facts = JSON.parse(factsText)
    } catch {
      throw new Error(`facts for '${entry.name}' are not valid JSON`)
    }
    try {
      catalog = JSON.parse(catalogText)
    } catch {
      throw new Error(`snapshot for '${entry.name}' is not valid JSON`)
    }
    inputs.push({ directory: entry.name, facts, catalog })
  }
  return inputs
}

async function writeModelsAtomically(modelsFile, document) {
  const directory = path.dirname(modelsFile)
  await mkdir(directory, { recursive: true })
  const temporary = path.join(directory, `.models.json.${process.pid}.${randomBytes(8).toString("hex")}.tmp`)
  try {
    const file = await open(temporary, "wx", 0o600)
    try {
      await file.writeFile(`${JSON.stringify(document, null, 2)}\n`)
      await file.sync()
    } finally {
      await file.close()
    }
    await rename(temporary, modelsFile)
    // Best-effort directory fsync: some platforms (notably Windows) refuse to
    // open a directory for fsync. The rename itself is still atomic.
    try {
      const handle = await open(directory, "r")
      try {
        await handle.sync()
      } finally {
        await handle.close()
      }
    } catch {
      // Intentionally ignored; see comment above.
    }
  } catch (error) {
    await rm(temporary, { force: true })
    throw error
  }
}

export async function applyModelsProjection(providerRoot, modelsFile) {
  const inputs = await loadProviderInputs(providerRoot)
  // Not-ready means "no authoritative generation yet", which is deliberately
  // distinct from "the provider set is empty". Leave existing config untouched.
  if (inputs === null) return "not-ready"
  await writeModelsAtomically(modelsFile, renderModels(inputs))
  return "authoritative"
}

function argument(name, fallback) {
  const index = process.argv.indexOf(name)
  return index === -1 ? fallback : process.argv[index + 1]
}

if (process.argv[1] !== undefined && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const providerRoot = argument("--provider-root", process.env.ACQ_PROVIDER_INPUT_ROOT ?? "/var/lib/acq/provider-input")
  const configDir = process.env.PI_CODING_AGENT_DIR ?? path.join(process.env.HOME ?? "/home/agent", ".pi", "agent")
  const modelsFile = argument("--models-file", path.join(configDir, "models.json"))
  applyModelsProjection(providerRoot, modelsFile)
    .then((status) => {
      if (status === "not-ready") {
        console.error(`pi-coding-agent: provider input not ready at ${providerRoot}; left ${modelsFile} unchanged`)
      }
    })
    .catch((error) => {
      console.error(`pi-coding-agent: ${error.message}`)
      process.exit(1)
    })
}
