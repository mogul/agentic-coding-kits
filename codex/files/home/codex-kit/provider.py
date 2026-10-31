"""Read acq's backend-owned provider generation, never an agent-owned catalog."""

import json
import math
import os
import re
from pathlib import Path
from urllib.parse import urlsplit


def strict_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON property")
            result[key] = value
        return result

    def invalid(_):
        raise ValueError("non-finite JSON value")

    def finite(raw):
        value = float(raw)
        if not math.isfinite(value):
            raise ValueError("non-finite JSON value")
        return value

    return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid, parse_float=finite)


def read(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 2_000_000:
        raise ValueError("provider input must be a bounded regular file")
    value = strict_json(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError("provider input must be an object")
    return value


def load(kind, env=None):
    env = os.environ if env is None else env
    root = Path(env.get("ACQ_PROVIDER_INPUT_ROOT", ""))
    if not root.is_absolute():
        raise ValueError("provider input root must be absolute")
    for path in (root, root / "models", root / "models/providers"):
        if path.is_symlink() or not path.is_dir():
            raise ValueError("provider input is not ready")
    directories = list((root / "models/providers").iterdir())
    if any(p.is_symlink() or not p.is_dir() for p in directories):
        raise ValueError("invalid provider directory")
    selected = env.get(f"ACQ_{kind}_PROVIDER")
    if selected is None and len(directories) == 1:
        selected = directories[0].name
    if not isinstance(selected, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,31}", selected):
        raise ValueError("select an unambiguous configured provider")
    facts_by_id = {p.name: read(p / "facts.json") for p in directories}
    for identity, facts in facts_by_id.items():
        url = urlsplit(facts.get("baseUrl", ""))
        key = facts.get("keyEnv", "")
        if (
            facts.get("schemaVersion") != "acq-provider-facts/v1"
            or facts.get("providerId") != identity
            or facts.get("apiProtocol") != "openai-compatible"
            or url.scheme != "https"
            or not url.hostname
            or url.hostname != facts.get("host")
            or url.username
            or url.password
            or url.query
            or url.fragment
            or not isinstance(key, str)
            or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key)
            or key == "GITHUB_TOKEN"
        ):
            raise ValueError("invalid provider facts")
    if selected not in facts_by_id:
        raise ValueError("selected provider is absent")
    facts = facts_by_id[selected]
    catalog = read(root / "models/providers" / selected / "snapshot.json")
    if catalog.get("schemaVersion") != "acq-neutral-model-catalog/v1" or catalog.get("providerId") != selected:
        raise ValueError("catalog identity mismatch")
    models = catalog.get("models")
    if not isinstance(models, list) or not 1 <= len(models) <= 500:
        raise ValueError("invalid model list")
    ids = []
    for model in models:
        value = model.get("id") if isinstance(model, dict) else None
        if (
            not isinstance(value, str)
            or not 1 <= len(value) <= 128
            or re.search(r"[\x00-\x1f\x7f\u2028\u2029]", value)
            or value in ids
        ):
            raise ValueError("invalid or duplicate model ID")
        ids.append(value)
    recommendations = catalog.get("recommendations", {})
    if not isinstance(recommendations, dict) or any(v not in ids for v in recommendations.values()):
        raise ValueError("invalid recommendations")
    primary = env.get(f"ACQ_{kind}_MODEL") or recommendations.get("primary") or (ids[0] if len(ids) == 1 else None)
    small = env.get(f"ACQ_{kind}_SMALL_MODEL") or recommendations.get("small") or primary
    if primary not in ids or small not in ids or not env.get(facts["keyEnv"]):
        raise ValueError("select a configured model and inject its credential")
    return facts, models, primary, small, {f["keyEnv"] for f in facts_by_id.values()}
