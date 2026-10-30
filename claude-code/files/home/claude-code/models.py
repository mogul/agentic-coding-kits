"""Claude-owned picker and restrictions derived from the selected acq catalog."""

from pathlib import Path

from provider import strict_json

# Explicit same-version deployment equivalents, not fuzzy name normalization.
# Never add extended-context suffixes or map unavailable Fable to another family.
CANONICAL_EQUIVALENTS = {
    "claude-sonnet-5-5": "claude-sonnet-5.5",
    "claude-opus-4-8": "claude_4_8_opus",
    "claude-opus-4-7": "claude_4_7_opus",
    "claude-sonnet-4-6": "claude_4_6_sonnet",
    "claude-sonnet-4-5": "claude_4_5_sonnet",
    "claude-haiku-4-5": "claude_4_5_haiku",
}


def model_overrides(ids):
    return {source: target for source, target in CANONICAL_EQUIVALENTS.items() if target in ids and source not in ids}


def compose_settings(args, ids, roles):
    remaining = []
    settings = {}
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--":
            remaining.extend(args[index:])
            break
        if arg == "--model" or arg.startswith("--model="):
            value = args[index + 1] if arg == "--model" and index + 1 < len(args) else arg.partition("=")[2]
            if (
                value not in ids
                and value not in model_overrides(ids)
                and value not in ("default", "sonnet", "opus", "haiku")
            ):
                raise ValueError("explicit model must be an exact gateway ID or configured role alias")
        if arg == "--settings" or arg.startswith("--settings="):
            if arg == "--settings":
                index += 1
                if index >= len(args):
                    raise ValueError("missing --settings value")
                value = args[index]
            else:
                value = arg.split("=", 1)[1]
            parsed = strict_json(value if value.lstrip().startswith("{") else Path(value).read_text())
            if not isinstance(parsed, dict):
                raise ValueError("Claude settings must be an object")
            settings.update(parsed)
        else:
            remaining.append(arg)
        index += 1
    # Preserve SDK hooks/permissions/env; own only model selection fields.
    settings.update(model_settings(ids, roles))
    return remaining, settings


def settings_argv(args, path):
    index = args.index("--") if "--" in args else len(args)
    return [*args[:index], "--settings", str(path), *args[index:]]


def model_settings(ids, roles):
    # Exact gateway IDs avoid fuzzy family/version mappings and unavailable aliases.
    return {
        "model": roles["primary"],
        "availableModels": [*ids, *model_overrides(ids)],
        "modelOverrides": model_overrides(ids),
        "enforceAvailableModels": True,
        "modelPicker": {
            "replaceBuiltInOptions": True,
            "options": [{"model": model, "label": model} for model in ids],
        },
    }
