#!/usr/bin/env python3
"""Validate every root kit using the locally checked-out, pinned Patterns release.

No network access: provision .patterns separately. Synthetic layout adapts this
repository's root directories to the upstream validator without changing specs.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

PATTERNS_REF = "a290d5d80737fc739e7ec139da0eeaf438631631"
REQUIRED_KITS = {"opencode-go-provider", "pi-coding-agent", "first-mate-skill", "claude-code"}


def require_file(path: Path) -> Path:
    if not path.is_file():
        raise ValueError(f"required validation input missing: {path}")
    return path


def discover_kits(root: Path) -> list[Path]:
    kits = sorted(path for path in root.iterdir() if path.is_dir() and (path / "spec.yaml").is_file())
    missing = REQUIRED_KITS - {path.name for path in kits}
    if missing:
        raise ValueError(f"required kit directories missing: {', '.join(sorted(missing))}")
    return kits


def validate_local_docs_and_modes(kit: Path) -> None:
    for document in kit.rglob("*.md"):
        if any(part in {"node_modules", "__pycache__", ".pytest_cache"} for part in document.parts):
            continue
        for target in re.findall(r"\]\(([^)\s]+)\)", document.read_text(encoding="utf-8")):
            if "://" in target or target.startswith(("#", "mailto:")):
                continue
            if not (document.parent / target.split("#", 1)[0]).exists():
                raise ValueError(f"{document}: broken local link {target}")
    # Check source permissions as well as declared guest permissions. Modes on
    # host-side normalizers matter before kit materialization begins.
    manifest = kit / "provider-input.json"
    if manifest.exists():
        bundle = json.loads(manifest.read_text(encoding="utf-8"))
        if not isinstance(bundle, dict) or not isinstance(bundle.get("normalizerPath"), str):
            raise ValueError(f"{kit.name}: provider manifest requires normalizerPath")
        normalizer = kit / bundle["normalizerPath"]
        if not normalizer.is_file() or not normalizer.stat().st_mode & 0o111:
            raise ValueError(f"{kit.name}: normalizer must be executable on disk")
    spec = yaml.safe_load((kit / "spec.yaml").read_text(encoding="utf-8"))
    if isinstance(spec, dict):
        for entry in spec.get("files", []):
            if not isinstance(entry, dict):
                continue
            try:
                executable = int(str(entry.get("mode", "0")), 8) & 0o111
            except ValueError:
                raise ValueError(f"{kit.name}: invalid payload mode") from None
            if "source" in entry and executable:
                source = kit / entry["source"]
                if source.is_file() and not source.stat().st_mode & 0o111:
                    raise ValueError(f"{kit.name}: executable payload lacks host execute permission: {entry['source']}")


def stage_kits(root: Path, patterns: Path, work: Path) -> Path:
    kits_dir = work / "integrations/isolation/acq-kits"
    kits_dir.mkdir(parents=True)
    (work / "schemas").mkdir()
    shutil.copy2(require_file(patterns / "schemas/kit-hybrid-v1.schema.json"), work / "schemas")
    registry = {}
    for kit in discover_kits(root):
        validate_local_docs_and_modes(kit)
        spec = yaml.safe_load((kit / "spec.yaml").read_text(encoding="utf-8"))
        if not isinstance(spec, dict) or spec.get("name") != kit.name:
            raise ValueError(f"{kit.name}: spec name must match its root directory")
        # Symlinks retain all payload paths, including hidden files, with no copies
        # of node_modules/ or virtual environments into the temporary tree.
        (kits_dir / kit.name).symlink_to(kit.resolve(), target_is_directory=True)
        registry[kit.name] = {"backends": ["sbx", "msb"], "parity": "CI validation entry."}
    (kits_dir / "kits.yaml").write_text(
        yaml.safe_dump({"schemaVersion": "acq-kits-registry/v1", "kits": registry}), encoding="utf-8"
    )
    return work


def validate(root: Path, patterns: Path) -> None:
    git = shutil.which("git")
    if git is None:
        raise ValueError("git is required to verify the Patterns checkout")
    actual = subprocess.run(
        [git, "-C", str(patterns), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    if actual != PATTERNS_REF:
        raise ValueError(f"Patterns checkout must be pinned to {PATTERNS_REF}, got {actual}")
    validator = require_file(patterns / "integrations/isolation/acq-kits/validate-kits.py")
    provider_validator = require_file(patterns / "scripts/validate_provider_input_contract.py")
    schema_dir = patterns / "integrations/isolation/schemas"
    bindings_source = require_file(schema_dir / "provider-credential-bindings.json")
    with tempfile.TemporaryDirectory(prefix="kit-validation-") as temporary:
        work = Path(temporary)
        stage_kits(root, patterns, work)
        subprocess.run([sys.executable, str(validator), "--root", str(work), "--strict"], check=True)
        # Preserve the preview provider's binding patch, not a relaxed validator.
        bindings = json.loads(bindings_source.read_text(encoding="utf-8"))
        bindings["providers"]["opencode-go"] = "OPENCODE_GO_API_KEY"
        bindings_path = work / "provider-credential-bindings.json"
        bindings_path.write_text(json.dumps(bindings, indent=2) + "\n", encoding="utf-8")
        bundles = [
            kit / "provider-input.json" for kit in discover_kits(root) if (kit / "provider-input.json").is_file()
        ]
        if not bundles:
            raise ValueError("no provider input bundles found")
        command = [
            sys.executable,
            str(provider_validator),
            "--schema-dir",
            str(schema_dir),
            "--credential-bindings",
            str(bindings_path),
        ]
        for bundle in bundles:
            command.extend(["--bundle", str(bundle)])
        subprocess.run(command, check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--patterns", type=Path, help="local pinned checkout (default: ROOT/.patterns)")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        validate(root, args.patterns.resolve() if args.patterns else root / ".patterns")
    except (ValueError, OSError, subprocess.CalledProcessError, yaml.YAMLError) as error:
        print(f"kit validation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
