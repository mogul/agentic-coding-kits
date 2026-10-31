"""Codex-owned catalog: exact provider IDs, conservative function-tool metadata."""


def codex_catalog(models):
    return {
        "models": [
            {
                "slug": model["id"],
                "display_name": model["id"],
                "description": "Configured Chat Completions deployment",
                "supported_reasoning_levels": [],
                "shell_type": "shell_command",
                "visibility": "list",
                "supported_in_api": True,
                "priority": index,
                "availability_nux": None,
                "upgrade": None,
                "support_verbosity": False,
                "default_verbosity": None,
                "apply_patch_tool_type": None,
                "truncation_policy": {"mode": "bytes", "limit": 10000},
                "experimental_supported_tools": [],
                "input_modalities": ["text"],
                "supports_reasoning_summary_parameter": False,
                "node_repl_disabled": True,
                "include_apps_usage_instructions": False,
                "base_instructions": (
                    "You are a coding assistant. Follow the user's task and workspace instructions. "
                    "Use the supplied function tools when needed, respect permission decisions, "
                    "verify changes, and report failures honestly."
                ),
            }
            for index, model in enumerate(models)
        ]
    }
