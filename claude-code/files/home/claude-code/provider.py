"""Resolve only backend-owned, provider-neutral facts; never persist credentials."""

import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit


def strict_json(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON property")
            result[key] = value
        return result

    def reject_constant(_):
        raise ValueError("non-finite JSON constant")

    return json.loads(text, object_pairs_hook=unique, parse_constant=reject_constant)


def credential_names(environ):
    """Read credential names for ALL projected providers, never their values."""
    root = Path(environ["ACQ_PROVIDER_INPUT_ROOT"]) / "models/providers"
    names = set()
    for directory in root.iterdir():
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("invalid provider directory")
        facts = read_input(directory / "facts.json")
        validate_facts(facts, directory.name)
        names.add(facts["keyEnv"])
    return names


def read_input(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("provider input must be a regular, non-symlink file")
    if path.stat().st_size > 2_000_000:
        raise ValueError("provider input exceeds size limit")
    result = strict_json(path.read_text())
    if not isinstance(result, dict):
        raise ValueError("provider input must be an object")
    return result


def validate_facts(facts, provider_id):
    if facts.get("schemaVersion") != "acq-provider-facts/v1":
        raise ValueError("unsupported provider facts version")
    if facts.get("providerId") != provider_id:
        raise ValueError("provider directory and identity disagree")
    if facts.get("apiProtocol") != "openai-compatible":
        raise ValueError("Claude kit requires an OpenAI-compatible provider")
    url = urlsplit(facts.get("baseUrl", ""))
    if (
        url.scheme != "https"
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.hostname != facts.get("host")
    ):
        raise ValueError("provider baseUrl must be HTTPS and agree with host")
    key_env = facts.get("keyEnv", "")
    if not isinstance(key_env, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key_env):
        raise ValueError("invalid credential environment name")
    if key_env == "GITHUB_TOKEN":
        raise ValueError("GitHub credentials are not model credentials")


def model_ids(catalog, provider_id):
    if catalog.get("schemaVersion") != "acq-neutral-model-catalog/v1" or catalog.get("providerId") != provider_id:
        raise ValueError("catalog version or identity mismatch")
    models = catalog.get("models")
    if not isinstance(models, list) or len(models) > 500:
        raise ValueError("invalid model list")
    ids = []
    for model in models:
        value = model.get("id") if isinstance(model, dict) else None
        if not isinstance(value, str) or not 1 <= len(value) <= 128 or re.search(r"[\x00-\x1f\x7f\u2028\u2029]", value):
            raise ValueError("invalid model ID")
        if value in ids:
            raise ValueError("duplicate model ID")
        ids.append(value)
    return ids


def choose_models(catalog, ids, environ):
    recommendations = catalog.get("recommendations", {})
    if not isinstance(recommendations, dict):
        raise ValueError("invalid recommendations")
    if any(value not in ids for value in recommendations.values()):
        raise ValueError("recommendation references an absent model")
    primary = environ.get("ACQ_CLAUDE_MODEL") or recommendations.get("primary")
    if primary is None and len(ids) == 1:
        primary = ids[0]
    small = environ.get("ACQ_CLAUDE_SMALL_MODEL") or recommendations.get("small") or primary
    opus = environ.get("ACQ_CLAUDE_OPUS_MODEL") or primary
    if any(value not in ids for value in (primary, small, opus)):
        raise ValueError("select valid ACQ_CLAUDE_MODEL/SMALL_MODEL/OPUS_MODEL values")
    return {"primary": primary, "small": small, "opus": opus}


def load_provider(environ=None):
    environ = os.environ if environ is None else environ
    root_value = environ.get("ACQ_PROVIDER_INPUT_ROOT", "")
    root = Path(root_value)
    if not root_value or not root.is_absolute() or root.is_symlink():
        raise ValueError("ACQ_PROVIDER_INPUT_ROOT is not ready")
    providers = root / "models" / "providers"
    for location in (root / "models", providers):
        if location.is_symlink() or not location.is_dir():
            raise ValueError("authoritative provider directory is not ready")
    candidates = sorted(providers.iterdir())
    if any(p.is_symlink() or not p.is_dir() for p in candidates):
        raise ValueError("invalid provider directory entry")
    selected = environ.get("ACQ_CLAUDE_PROVIDER")
    if selected is None and len(candidates) == 1:
        selected = candidates[0].name
    if not isinstance(selected, str) or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?", selected):
        raise ValueError("select ACQ_CLAUDE_PROVIDER when providers are empty or ambiguous")
    directory = providers / selected
    if directory not in candidates:
        raise ValueError("selected provider is absent")
    facts = read_input(directory / "facts.json")
    validate_facts(facts, selected)
    catalog = read_input(directory / "snapshot.json")
    ids = model_ids(catalog, selected)
    roles = choose_models(catalog, ids, environ)
    if not environ.get(facts["keyEnv"]):
        raise ValueError("selected provider credential is not injected")
    return facts, ids, roles
