#!/usr/bin/env python3
"""Offline regression tests for generated provenance and local export policy."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

sys.dont_write_bytecode = True

KIT = Path(__file__).resolve().parents[1]
SKILL = KIT / "files/home/.agents/skills/diagram-design"
GUARD = SKILL / "scripts/export_diagram.py"
spec = importlib.util.spec_from_file_location("export_guard", GUARD)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

DOCUMENT = """<!doctype html><html><head><meta charset="utf-8"><title>Diagram</title>
<style>body{margin:0}svg{display:block}</style></head><body><main>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 120" role="img" aria-labelledby="test-title test-desc">
<title id="test-title">Test diagram</title><desc id="test-desc">A single rectangle.</desc>
<rect x="40" y="40" width="120" height="40" fill="#fff" stroke="#000"/>
</svg></main></body></html>"""


def assert_inventory(root: Path, locked: set[str]) -> None:
    payload = root / "files/home/.agents/skills/diagram-design"
    actual = {p.relative_to(root).as_posix() for p in payload.rglob("*") if p.is_file()}
    actual.add("files/home/.agents/licenses/diagram-design-LICENSE")
    if actual != locked:
        raise ValueError(f"Diagram Design inventory differs: extra={actual - locked}, missing={locked - actual}")


class PolicyTests(unittest.TestCase):
    def test_import_helpers_synthetic_smoke(self):
        fixtures = {
            "mermaid_extract.py": ("flow.mmd", "flowchart LR\n A[Client] --> B[Server]\n"),
            "plantuml_extract.py": ("sequence.puml", "@startuml\nAlice -> Bob: Hello\n@enduml\n"),
            "excalidraw_extract.py": ("scene.excalidraw", '{"type":"excalidraw","version":2,"elements":[]}'),
            "drawio_extract.py": (
                "diagram.drawio",
                '<mxfile><diagram name="Page"><mxGraphModel><root><mxCell id="0"/>'
                '<mxCell id="1" parent="0"/></root></mxGraphModel></diagram></mxfile>',
            ),
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for helper, (filename, text) in fixtures.items():
                source = root / filename
                source.write_text(text)
                result = subprocess.run(  # noqa: S603 -- pinned helper and synthetic local data
                    [sys.executable, str(SKILL / "scripts" / helper), str(source)],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("IR", result.stdout)

    def test_simple_document(self):
        guard.validate(DOCUMENT.encode(), 2)

    def test_resource_and_active_content_denied(self):
        for injection in [
            '<img src="https://example.com/x">',
            '<iframe src="file:///etc/passwd"></iframe>',
            '<meta http-equiv="refresh" content="0;url=https://example.com">',
            '<script>fetch("https://example.com")</script>',
            '<base href="file:///">',
            '<style>@import "https://example.com";</style>',
            "<style>body{background:url(https://example.com)}</style>",
            "<style>body{background:u/**/rl(https://example.com)}</style>",
            "<style>body{background:u\\72l(https://example.com)}</style>",
            '<svg onload="alert(1)" viewBox="0 0 1 1"></svg>',
            '<object data="file:///etc/passwd"></object>',
        ]:
            with self.subTest(injection=injection), self.assertRaises(ValueError):
                guard.validate(DOCUMENT.replace("</head>", injection + "</head>").encode(), 2)

    def test_depth_nodes_dimensions(self):
        for value in [
            DOCUMENT.replace("200 120", "999999 999999"),
            DOCUMENT.replace("<main>", "<main>" + "<div>" * 65),
            DOCUMENT.replace("</main>", "<br>" * 20_001 + "</main>"),
        ]:
            with self.assertRaises(ValueError):
                guard.validate(value.encode(), 2)

    def test_templates_are_offline(self):
        for path in (SKILL / "assets").glob("template*.html"):
            self.assertNotIn("fonts.googleapis.com", path.read_text())
            guard.validate(path.read_bytes(), 2)

    def test_motion_controller_tampering(self):
        source = (SKILL / "assets/template-motion.html").read_text()
        with self.assertRaises(ValueError):
            guard.validate(
                source.replace(
                    "<script data-diagram-controls>", "<script data-diagram-controls>fetch('https://example.com');"
                ).encode(),
                2,
            )

    def test_svg_policy_and_input_bounds(self):
        svg = '<svg viewBox="0 0 200 120"><title>Test</title></svg>'
        guard.validate(svg.encode(), 2, svg_only=True)
        with self.assertRaises(ValueError):
            guard.validate(
                svg.replace("</svg>", "<script data-diagram-controls></script></svg>").encode(), 2, svg_only=True
            )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "large.html"
            path.write_bytes(b"x" * (guard.MAX_INPUT + 1))
            with self.assertRaises(ValueError):
                guard.read_bounded(path)

    def test_xml_entity_obfuscated_resources(self):
        hostile = "<style>rect{fill:&#117;rl(https&#58;&#47;&#47;example.com/x.svg#x)}</style>"
        with self.assertRaises(ValueError):
            guard.validate(DOCUMENT.replace("</svg>", hostile + "</svg>").encode(), 2)
        for extra in [
            hostile,
            "<style><![CDATA[rect{fill:url(https://example.com/x)}]]></style>",
            '<rect fill="&#117;rl(https&#58;//example.com/x)"/>',
        ]:
            svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 120">{extra}</svg>'
            with self.assertRaises(ValueError):
                guard.validate(svg.encode(), 2, svg_only=True)
        for prefix in ['<?xml-stylesheet href="https://example.com/x"?>', '<!DOCTYPE svg [<!ENTITY x "external">]>']:
            with self.assertRaises(ValueError):
                guard.validate((prefix + '<svg viewBox="0 0 200 120"/>').encode(), 2, svg_only=True)

    def test_entity_attack_cli_produces_no_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            hostile = "<style>rect{fill:&#117;rl(https&#58;&#47;&#47;example.com/x.svg#x)}</style>"
            (root / "diagram.html").write_text(DOCUMENT.replace("</svg>", hostile + "</svg>"))
            result = subprocess.run(  # noqa: S603 -- fixed guard with synthetic data
                [sys.executable, str(GUARD), "diagram.html", "diagram.svg"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((root / "diagram.svg").exists())

    def test_quoted_comment_resource_attack(self):
        hostile = '<style>rect{--before:"/*";fill:&#117;rl(&#47;&#47;example.com/x.svg#x);--after:"*/"}</style>'
        with self.assertRaises(ValueError):
            guard.validate(DOCUMENT.replace("</svg>", hostile + "</svg>").encode(), 2)
        svg = (
            '<svg viewBox="0 0 200 120"><style><![CDATA['
            'rect{--before:"/*";fill:url(//example.com/x);--after:"*/"}]]></style></svg>'
        )
        with self.assertRaises(ValueError):
            guard.validate(svg.encode(), 2, svg_only=True)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "diagram.html").write_text(DOCUMENT.replace("</svg>", hostile + "</svg>"))
            result = subprocess.run(  # noqa: S603 -- fixed guard and synthetic malicious input
                [sys.executable, str(GUARD), "diagram.html", "diagram.svg"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((root / "diagram.svg").exists())

    def test_css_string_newline_attack(self):
        for newline in ["\n", "\r", "\f"]:
            hostile = (
                '<style>rect{--a:"' + newline + '"/*";fill:&#117;rl(&#47;&#47;example.com/x.svg#x);--z:"*/"";}</style>'
            )
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "diagram.html").write_text(DOCUMENT.replace("</svg>", hostile + "</svg>"))
                result = subprocess.run(  # noqa: S603 -- fixed guard and adversarial synthetic data
                    [sys.executable, str(GUARD), "diagram.html", "diagram.svg"],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((root / "diagram.svg").exists())

    def test_export_warnings_withhold_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "diagram.html").write_text(
                DOCUMENT.replace("</svg>", "<style>@page{margin:1cm}rect{fill:red}</style></svg>")
            )
            result = subprocess.run(  # noqa: S603 -- fixed guard and warning fixture
                [sys.executable, str(GUARD), "diagram.html", "diagram.svg"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("export_warning", result.stdout)
            self.assertFalse((root / "diagram.svg").exists())

    def test_no_competing_skill_instructions(self):
        skill = (SKILL / "SKILL.md").read_text()
        for stale in [
            "getComputedStyle",
            "external except Google Fonts",
            "Browse the gallery",
            "python3 <repo-root>/scripts/verify-motion.py",
        ]:
            self.assertNotIn(stale, skill)
        style = (SKILL / "references/style-guide.md").read_text()
        for stale in [
            "ships in the font link above",
            "Both Noto faces ship",
            "Both Noto TC faces ship",
            "every shipped template and example is already checked",
        ]:
            self.assertNotIn(stale, style)
        self.assertNotIn(
            "only external stylesheet allowed is Google Fonts", (SKILL / "references/type-polar.md").read_text()
        )

    def test_browser_release_gate_closed(self):
        self.assertFalse(guard.BROWSER_EXPORT_VALIDATED)

    def test_unlocked_payload_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / "files/home/.agents/skills/diagram-design"
            payload.mkdir(parents=True)
            (payload / "SKILL.md").write_text("synthetic")
            locked = {
                "files/home/.agents/skills/diagram-design/SKILL.md",
                "files/home/.agents/licenses/diagram-design-LICENSE",
            }
            assert_inventory(root, locked)
            (payload / "installer.py").write_text("synthetic unapproved file")
            with self.assertRaises(ValueError):
                assert_inventory(root, locked)

    def test_local_reference_links(self):
        import re

        for path in SKILL.rglob("*.md"):
            for target in re.findall(r"\]\(([^ )]+)\)", path.read_text()):
                if ":" not in target and not target.startswith("#"):
                    self.assertTrue((path.parent / target.split("#")[0]).exists(), (path, target))

    def test_provenance_and_local_mirrors(self):
        import hashlib

        lock = json.loads((KIT / "vendor/diagram-design.json").read_text())
        self.assertEqual(lock["ref"], "f2496acbde9f45ccb55c24d4f75210c8a1355df8")
        for rel, digest in lock["files"].items():
            self.assertEqual(hashlib.sha256((KIT / rel).read_bytes()).hexdigest(), digest, rel)
        assert_inventory(KIT, set(lock["files"]))
        self.assertEqual(len(lock["sourceSha256"]), 78)
        self.assertEqual(
            lock["thirdParty"][0]["licenseSha256"], lock["files"]["files/home/.agents/licenses/diagram-design-LICENSE"]
        )
        vendor_spec = importlib.util.spec_from_loader(
            "diagram_vendor",
            SourceFileLoader("diagram_vendor", str(KIT / "scripts/vendor-diagram-design")),
        )
        vendor = importlib.util.module_from_spec(vendor_spec)
        vendor_spec.loader.exec_module(vendor)
        expected_sources = {"LICENSE"} | {"skills/diagram-design/" + rel for rel in vendor.SELECTED_SOURCE_PATHS}
        self.assertEqual(set(lock["sourceSha256"]), expected_sources)
        local = KIT / "vendor/diagram-design-local"
        for path in local.rglob("*"):
            if path.is_file():
                self.assertEqual(path.read_bytes(), (SKILL / path.relative_to(local)).read_bytes())

    def test_cli_export_and_denial(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "diagram.html").write_text(DOCUMENT)

            def run(*args):
                return subprocess.run(  # noqa: S603 -- fixed local helper and synthetic arguments
                    [sys.executable, str(GUARD), *args], cwd=root, capture_output=True, text=True, timeout=30
                )

            denied = run("diagram.html", "diagram.png")
            self.assertNotEqual(denied.returncode, 0)
            self.assertIn("DENIED", denied.stdout)
            self.assertFalse((root / "diagram.png").exists())
            blocked = run("diagram.html", "diagram.png", "--approve-browser-export")
            self.assertNotEqual(blocked.returncode, 0)
            self.assertIn("BLOCKED", blocked.stdout)
            result = run("diagram.html", "diagram.svg")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("fonts.googleapis.com", (root / "diagram.svg").read_text())
            self.assertNotEqual(run("diagram.html", "diagram.svg").returncode, 0)
            (root / "linked.html").symlink_to(root / "diagram.html")
            self.assertNotEqual(run("linked.html", "linked.svg").returncode, 0)
            self.assertNotEqual(run("../diagram.html", "bad.svg").returncode, 0)

    def test_direct_upstream_cli_disabled(self):
        result = subprocess.run(  # noqa: S603 -- fixed local CLI refusal test
            [sys.executable, str(SKILL / "scripts/upstream_export_svg.py")], capture_output=True, text=True
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("direct SVG export is disabled", result.stderr)


if __name__ == "__main__":
    unittest.main()
