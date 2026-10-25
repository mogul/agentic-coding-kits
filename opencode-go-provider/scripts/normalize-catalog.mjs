#!/usr/bin/env node
//
// normalize-catalog.mjs — convert an offline capture of the OpenCode Go models
// endpoint into the acq-neutral, cross-provider model-catalog shape
// ("acq-neutral-model-catalog/v1") this kit vendors and ships as a snapshot.
//
// Input shape: a JSON document shaped like the OpenAI-style models endpoint
// (https://opencode.ai/inference/go/v1/models), i.e. an object with a `data`
// array of model records:
//
//   { "object": "list", "data": [ { "id": "...", "object": "model", ... } ] }
//
// The LIVE endpoint returns ids only (plus object/created/owned_by). Pricing and
// limits are published separately at https://opencode.ai/docs/go, so an
// authoring input is an annotated capture: each record MAY also carry `name`,
// `contextWindow`, `maxOutputTokens`, and `cost` in the same field names the
// neutral schema uses. This script copies those fields verbatim and drops the
// endpoint-envelope fields (`object`, `created`, `owned_by`, `capturedAt`,
// `note`), which the neutral v1 shape does not model.
//
// This is a HOST-SIDE authoring tool (it lives under scripts/, not files/). It
// is pure in spirit: reads exactly one file, writes exactly one file, makes no
// network calls, and has no other side effects. Fetching the live endpoint and
// annotating pricing is a separate, human-gated step; this tool only reshapes an
// already-produced capture so the transform is reviewable and testable.
//
// SCOPE DECISION: this kit declares apiProtocol `openai-compatible` only, so the
// source capture must already be restricted to models served over
// /openai/v1/chat/completions. OpenCode Go routes other models over Anthropic-,
// Google-, and OpenAI-Responses-shaped endpoints; including one here would
// advertise a model that this provider input cannot route. The normalizer does
// not attempt to infer a protocol from an id — that knowledge lives in the
// capture and in tests/fixtures/normalize-source.json.
//
// UNIT-CONVENTION DECISION: prices are USD per 1M tokens and are passed through
// UNCHANGED (no /1e6 or *1e6 transform). The neutral schema documents
// `cost` as per-million-token pricing, so no transform is needed, nothing is
// rounded, and the output is a faithful re-shape of its source. Convert at the
// READ site if a future consumer needs per-token values.
//
// PEAK PRICING: the neutral v1 shape has no time-of-day tiering. DeepSeek
// models publish peak and off-peak prices; this catalog records the OFF-PEAK
// price in `cost` and documents the peak price in the README. Consumers cannot
// express the peak window in this schema, so the lower, baseline price is the
// only defensible single value.
//
// MUTABILITY: the shipped snapshot lands at an agent-owned path
// (/home/agent/...). It is model METADATA only: no host, baseUrl, modelsUrl,
// keyEnv, or apiKey fields. Rewriting it cannot redirect a credential.
//
// Usage:
//   node normalize-catalog.mjs [--source <path>] [--out <path>]
//     --source  default: <kit>/tests/fixtures/normalize-source.json
//     --out     default: <kit>/files/home/opencode-go/model-catalog-snapshot.json
//               tests/fixtures/ holds hand-authored test INPUTS; the snapshot
//               path holds the GENERATED artifact that ships. Regenerating the
//               snapshot is an explicit, reviewable action (`npm run
//               sync:opencode-go-models`), and `npm test` fails if the checked-in
//               snapshot drifts from normalizer output.
//
// Both defaults resolve relative to this script's own directory, so they work
// regardless of the caller's cwd.

import { mkdir, readFile, writeFile } from "node:fs/promises"
import path from "node:path"
import process from "node:process"
import { fileURLToPath } from "node:url"

// This file lives at <kit>/scripts/normalize-catalog.mjs.
const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url))
const KIT_ROOT = path.resolve(SCRIPT_DIR, "..")
const DEFAULT_SOURCE_PATH = path.join(KIT_ROOT, "tests/fixtures/normalize-source.json")
const DEFAULT_OUT_PATH = path.join(KIT_ROOT, "files/home/opencode-go/model-catalog-snapshot.json")

const NEUTRAL_SCHEMA_VERSION = "acq-neutral-model-catalog/v1"
const PROVIDER_ID = "opencode-go"
const MODEL_ID_PATTERN = /^[^\u0000-\u001F\u007F\u2028\u2029]+$/
const MODEL_NAME_PATTERN = /^[^\u0000-\u001F\u007F\u2028\u2029]+$/
const MAX_MODELS = 500
const RECOMMENDATION_ROLES = ["primary", "small", "compaction", "summary", "title"]
const COST_KEYS = ["input", "output", "cacheRead", "cacheWrite"]

function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value)
}

function describe(value) {
  return value === undefined ? "undefined" : JSON.stringify(value)
}

function requirePositiveInteger(value, name) {
  if (!Number.isInteger(value) || value <= 0) {
    throw new Error(`${name} must be a positive integer`)
  }
}

function requireNonNegativeFiniteNumber(value, name) {
  if (!Number.isFinite(value) || value < 0) {
    throw new Error(`${name} must be a non-negative finite number`)
  }
}

/**
 * Re-shape one models-endpoint record into the neutral per-model shape.
 * Field names are reused verbatim from the neutral schema (contextWindow,
 * maxOutputTokens, cost.{input,output,cacheRead,cacheWrite}); endpoint-envelope
 * fields are dropped.
 * @param {object} model - one entry from the source capture's `data[]`
 * @param {number} index - position, for actionable error messages
 * @returns {{id: string, name?: string, contextWindow?: number, maxOutputTokens?: number, cost?: object}}
 */
function normalizeModel(model, index) {
  const prefix = `data[${index}]`
  if (!isPlainObject(model)) {
    throw new Error(`${prefix} must be an object (got ${describe(model)})`)
  }
  if (typeof model.id !== "string" || model.id.length === 0) {
    throw new Error(`${prefix}.id must be a non-empty string (got ${describe(model.id)})`)
  }
  if (model.id.length > 128 || !MODEL_ID_PATTERN.test(model.id)) {
    throw new Error(`${prefix}.id is not a valid neutral model identifier`)
  }

  const out = { id: model.id }
  if (model.name !== undefined) {
    if (typeof model.name !== "string" || model.name.length === 0) {
      throw new Error(`${prefix}.name must be a non-empty string (got ${describe(model.name)})`)
    }
    if (model.name.length > 256 || !MODEL_NAME_PATTERN.test(model.name)) {
      throw new Error(`${prefix}.name is not a valid model display name`)
    }
    out.name = model.name
  }
  if (model.contextWindow !== undefined) {
    requirePositiveInteger(model.contextWindow, `${prefix}.contextWindow`)
    out.contextWindow = model.contextWindow
  }
  if (model.maxOutputTokens !== undefined) {
    requirePositiveInteger(model.maxOutputTokens, `${prefix}.maxOutputTokens`)
    out.maxOutputTokens = model.maxOutputTokens
  }
  if (model.cost !== undefined) {
    if (!isPlainObject(model.cost)) {
      throw new Error(`${prefix}.cost must be an object (got ${describe(model.cost)})`)
    }

    // Pass through unchanged — see the per-million-token decision above.
    // Only copy the scalar keys the neutral schema defines, so an unexpected
    // extra key on the source can't leak into the neutral output unnoticed.
    const cost = {}
    for (const key of COST_KEYS) {
      if (model.cost[key] !== undefined) {
        requireNonNegativeFiniteNumber(model.cost[key], `${prefix}.cost.${key}`)
        cost[key] = model.cost[key]
      }
    }
    if (Object.keys(cost).length > 0) {
      out.cost = cost
    }
  }
  if (model.costAbove200kContext !== undefined) {
    if (!isPlainObject(model.costAbove200kContext)) {
      throw new Error(`${prefix}.costAbove200kContext must be an object (got ${describe(model.costAbove200kContext)})`)
    }
    const tieredCost = {}
    for (const key of COST_KEYS) {
      if (model.costAbove200kContext[key] !== undefined) {
        requireNonNegativeFiniteNumber(
          model.costAbove200kContext[key],
          `${prefix}.costAbove200kContext.${key}`,
        )
        tieredCost[key] = model.costAbove200kContext[key]
      }
    }
    if (Object.keys(tieredCost).length > 0) {
      out.costAbove200kContext = tieredCost
    }
  }
  return out
}

/**
 * Convert a models-endpoint-shaped capture into the neutral
 * acq-neutral-model-catalog/v1 shape.
 * @param {object} sourceCatalog - parsed capture with a `data[]` array
 * @returns {object} the neutral catalog document
 */
export function normalizeCatalog(sourceCatalog) {
  if (!isPlainObject(sourceCatalog) || !Array.isArray(sourceCatalog.data)) {
    throw new Error("normalizeCatalog: source catalog is missing a data[] array")
  }
  const models = sourceCatalog.data
  if (models.length > MAX_MODELS) {
    throw new Error(`normalizeCatalog: data[] exceeds ${MAX_MODELS} entries`)
  }
  const ids = models.map((model) => model?.id)
  if (new Set(ids).size !== ids.length) {
    throw new Error("normalizeCatalog: source catalog contains duplicate model IDs")
  }
  const recommendations = sourceCatalog.recommendations
  if (recommendations !== undefined) {
    if (!isPlainObject(recommendations)) {
      throw new Error("normalizeCatalog: recommendations must be an object")
    }
    for (const [role, modelId] of Object.entries(recommendations)) {
      if (!RECOMMENDATION_ROLES.includes(role)) {
        throw new Error(`normalizeCatalog: unsupported recommendation role '${role}'`)
      }
      if (typeof modelId !== "string" || !ids.includes(modelId)) {
        throw new Error(`normalizeCatalog: recommendation '${role}' must reference a model id`)
      }
    }
  }
  return {
    schemaVersion: NEUTRAL_SCHEMA_VERSION,
    providerId: PROVIDER_ID,
    models: models.map(normalizeModel),
    ...(recommendations === undefined ? {} : { recommendations: { ...recommendations } }),
  }
}

function parseArgs(argv) {
  const args = { source: DEFAULT_SOURCE_PATH, out: DEFAULT_OUT_PATH }
  for (let i = 0; i < argv.length; i++) {
    const option = argv[i]
    if (option !== "--source" && option !== "--out") {
      throw new Error(`unknown option: ${option}`)
    }
    const value = argv[++i]
    if (value === undefined || value.startsWith("--")) {
      throw new Error(`${option} requires a path`)
    }
    args[option === "--source" ? "source" : "out"] = path.resolve(value)
  }
  return args
}

async function main() {
  const { source, out } = parseArgs(process.argv.slice(2))

  const sourceText = await readFile(source, "utf8")
  const sourceCatalog = JSON.parse(sourceText)
  const neutralCatalog = normalizeCatalog(sourceCatalog)

  await mkdir(path.dirname(out), { recursive: true })
  await writeFile(out, JSON.stringify(neutralCatalog, null, 2) + "\n")

  process.stdout.write(`Wrote ${neutralCatalog.models.length} normalized models to ${out}\n`)
}

// Portable "run as a script" guard. Comparing import.meta.url to a hand-built
// `file://${process.argv[1]}` string fails on Windows (backslash paths and the
// third slash in file:///C:/...), which silently turns a CLI invocation into a
// no-op. Resolving both sides avoids that.
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    console.error(`normalize-catalog: failed: ${error.message}`)
    process.exit(1)
  })
}
