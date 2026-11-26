#!/usr/bin/env python3
"""Validate a project-local diagram, then export SVG or approved isolated PNG.

AI-assisted local adaptation; MIT, this repository. No dependency installation.
The CLI approval flag is an audit acknowledgement, not an authentication system.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import resource
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

MAX_INPUT = 2 * 1024 * 1024
MAX_DEPTH = 64
MAX_NODES = 20_000
MAX_PIXELS = 16_000_000
MAX_OUTPUT = 32 * 1024 * 1024
# Release gate: only change after operator-provisioned Chromium passes live
# capture, namespace, sandbox, cleanup and aggregate resource-budget tests.
BROWSER_EXPORT_VALIDATED = False
ROOT = Path(__file__).resolve().parents[1]
VOID = {"meta", "link", "br", "hr", "img", "input", "wbr"}
TAGS = {
    "html",
    "head",
    "meta",
    "title",
    "style",
    "body",
    "main",
    "header",
    "footer",
    "section",
    "article",
    "div",
    "span",
    "p",
    "h1",
    "h2",
    "h3",
    "h4",
    "small",
    "strong",
    "em",
    "b",
    "i",
    "code",
    "pre",
    "ul",
    "ol",
    "li",
    "br",
    "hr",
    "button",
    "noscript",
    "script",
    "svg",
    "g",
    "defs",
    "rect",
    "circle",
    "ellipse",
    "line",
    "polyline",
    "polygon",
    "path",
    "text",
    "tspan",
    "desc",
    "marker",
    "clippath",
    "lineargradient",
    "radialgradient",
    "stop",
    "mask",
    "pattern",
    "use",
}


def audit(event: str, **values: object) -> None:
    print(
        json.dumps(
            {"at": datetime.now(UTC).isoformat(), "agent": "OpenCode AI", "event": event, **values}, sort_keys=True
        ),
        flush=True,
    )


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def css_without_comments(css: str) -> str:
    """Remove only real comments; quoted comment markers remain string data."""
    result: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(css):
        char = css[index]
        if char == "\\":
            raise ValueError("CSS escapes refused")
        if quote:
            if char in {"\n", "\r", "\f"}:
                raise ValueError("unescaped CSS string newline refused")
            if css.startswith(("/*", "*/"), index):
                raise ValueError("ambiguous CSS string comment markers refused")
            result.append(char)
            if char == quote:
                quote = None
            index += 1
        elif char in {"'", '"'}:
            quote = char
            result.append(char)
            index += 1
        elif css.startswith("/*", index):
            end = css.find("*/", index + 2)
            if end < 0:
                raise ValueError("unterminated CSS comment")
            index = end + 2
        else:
            result.append(char)
            index += 1
    if quote:
        raise ValueError("unterminated CSS string")
    return "".join(result)


def project_path(value: str, *, existing: bool) -> Path:
    path = Path(value)
    if path.is_absolute() or not path.parts or any(p in {"..", "."} for p in path.parts):
        raise ValueError("use a relative path inside the current project")
    if any(ord(c) < 32 for c in value) or "\\" in value:
        raise ValueError("unsafe project path")
    root = Path.cwd().resolve()
    target = root / path
    current = root
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("symlink paths are refused")
    if not target.parent.is_dir() or not target.parent.resolve().is_relative_to(root):
        raise ValueError("output/input parent must exist inside the project")
    if existing and not target.is_file():
        raise ValueError("input must be an ordinary project file")
    if not existing and target.exists():
        raise ValueError("existing output refused; select a new filename")
    return target


def read_bounded(path: Path, limit: int = MAX_INPUT) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        import stat

        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("input is not a regular file")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise ValueError("input exceeds byte limit")
        return data
    finally:
        os.close(fd)


class DocumentPolicy(HTMLParser):
    def __init__(self, controller: str, *, svg_only: bool = False):
        super().__init__(convert_charrefs=True)
        self.controller = controller
        self.svg_only = svg_only
        self.stack: list[str] = []
        self.nodes = 0
        self.svgs = 0
        self.dimensions: tuple[float, float] | None = None
        self.scripts: list[str] = []
        self.styles: list[str] = []
        self.script_parts: list[str] = []
        self.style_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.nodes += 1
        if self.nodes > MAX_NODES or len(self.stack) >= MAX_DEPTH:
            raise ValueError("document exceeds node/depth limit")
        if tag not in TAGS or (self.svg_only and tag in {"script", "html", "body", "head"}):
            raise ValueError(f"unsupported element: {tag}")
        names = [name for name, _ in attrs]
        if len(names) != len(set(names)):
            raise ValueError("duplicate attributes refused")
        values = dict(attrs)
        for name, value in attrs:
            value = (value or "").strip()
            if name.startswith("on") or name in {
                "src",
                "srcdoc",
                "action",
                "formaction",
                "background",
                "poster",
                "ping",
                "xml:base",
            }:
                raise ValueError("executable/resource attributes refused")
            if name == "http-equiv":
                raise ValueError("HTTP-equivalent meta directives refused")
            if name in {"href", "xlink:href"} and not re.fullmatch(r"#[A-Za-z][A-Za-z0-9_.:-]*", value):
                raise ValueError("only internal fragment references are permitted")
            if name == "style":
                self.styles.append(value)
        if tag == "script":
            if attrs != [("data-diagram-controls", None)]:
                raise ValueError("motion script attributes refused")
            self.script_parts = []
        if tag == "style":
            self.style_parts = []
        if tag == "svg":
            self.svgs += 1
            viewbox = values.get("viewbox", "") or ""
            try:
                numbers = [float(n) for n in re.split(r"[\s,]+", viewbox.strip())]
            except ValueError as error:
                raise ValueError("invalid viewBox") from error
            if len(numbers) != 4 or not all(math.isfinite(n) for n in numbers) or min(numbers[2:]) <= 0:
                raise ValueError("finite positive SVG dimensions required")
            self.dimensions = numbers[2], numbers[3]
        if tag not in VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if not self.stack or self.stack[-1] != tag:
            raise ValueError("unbalanced document elements")
        self.stack.pop()
        if tag == "script":
            self.scripts.append("".join(self.script_parts))
        if tag == "style":
            self.styles.append("".join(self.style_parts))

    def handle_data(self, data: str) -> None:
        if self.stack and self.stack[-1] == "script":
            self.script_parts.append(data)
        if self.stack and self.stack[-1] == "style":
            self.style_parts.append(data)

    def finish(self, scale: float) -> None:
        if self.stack or self.svgs != 1 or self.dimensions is None:
            raise ValueError("one complete SVG diagram required")
        if self.scripts and (len(self.scripts) != 1 or self.scripts[0].strip() != self.controller.strip()):
            raise ValueError("only the pinned motion controller is permitted")
        for css in self.styles:
            # Conservative lexical policy: reject escapes/comments that obscure
            # loader names; only url(#local-id) may reference another SVG node.
            css = css_without_comments(unescape(css))
            if "\\" in css or re.search(r"@import|@font-face|image-set|expression\s*\(|https?:|data:|file:", css, re.I):
                raise ValueError("CSS loaders/obfuscation refused")
            remainder = re.sub(r"url\(\s*['\"]?#[A-Za-z][A-Za-z0-9_.:-]*['\"]?\s*\)", "", css, flags=re.I)
            if re.search(r"url\s*\(", remainder, re.I):
                raise ValueError("external CSS resources refused")
        width, height = self.dimensions
        if max(width * scale, height * scale) > 8192 or width * height * scale * scale > MAX_PIXELS:
            raise ValueError("export exceeds pixel budget")


def validate(source: bytes, scale: float, *, svg_only: bool = False) -> None:
    if b"\0" in source:
        raise ValueError("NUL bytes refused")
    template = (ROOT / "assets/template-motion.html").read_text()
    controllers = re.findall(r"<script data-diagram-controls>(.*?)</script>", template, flags=re.S)
    if len(controllers) != 1:
        raise ValueError("pinned controller unavailable")
    policy = DocumentPolicy(controllers[0], svg_only=svg_only)
    policy.feed(source.decode("utf-8"))
    policy.close()
    policy.finish(scale)
    if svg_only:
        validate_svg_xml(source, controllers[0], scale)


def validate_svg_xml(source: bytes, controller: str, scale: float) -> None:
    """Check the exported document as XML, not HTML raw-style text."""
    text = source.decode("utf-8")
    if re.search(r"<!DOCTYPE|<!ENTITY|<\?(?!xml\s)", text, re.I):
        raise ValueError("SVG declarations or processing instructions refused")
    try:
        root = ElementTree.fromstring(text)  # noqa: S314 -- DTD/entities rejected, bytes bounded
    except ElementTree.ParseError as error:
        raise ValueError("invalid SVG XML") from error
    policy = DocumentPolicy(controller, svg_only=True)
    pending = [(root, False)]
    while pending:
        element, closing = pending.pop()
        tag = element.tag
        if tag.startswith("{"):
            namespace, tag = tag[1:].split("}", 1)
            if namespace != "http://www.w3.org/2000/svg":
                raise ValueError("unexpected SVG element namespace")
        tag = tag.lower()
        if closing:
            policy.handle_endtag(tag)
            continue
        attrs = []
        for name, value in element.attrib.items():
            if name.startswith("{"):
                namespace, name = name[1:].split("}", 1)
                if namespace == "http://www.w3.org/1999/xlink" and name == "href":
                    name = "xlink:href"
                else:
                    raise ValueError("unexpected SVG attribute namespace")
            attrs.append((name.lower(), value))
            # SVG presentation attributes have CSS semantics as well as style.
            if re.search(r"url\s*\(|\\|https?:|data:|file:", value, re.I):
                policy.styles.append(value)
        policy.handle_starttag(tag, attrs)
        if element.text:
            policy.handle_data(element.text)
        pending.append((element, True))
        pending.extend((child, False) for child in reversed(list(element)))
    policy.finish(scale)


def process_limits() -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_OUTPUT, MAX_OUTPUT))
    resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
    resource.setrlimit(resource.RLIMIT_AS, (4 * 1024**3, 4 * 1024**3))


def sandbox_command(runtime: Path, work: Path) -> list[str]:
    if sys.platform != "linux" or not shutil.which("bwrap"):
        raise ValueError("BLOCKED: Linux Bubblewrap isolation is required")
    runtime = runtime.resolve(strict=True)
    if runtime == Path("/") or runtime.is_relative_to(Path.cwd().resolve()):
        raise ValueError("BLOCKED: runtime must be separately provisioned outside the project")
    if not (runtime / "bin/python").is_file() or not (runtime / "chromium/chrome").is_file():
        raise ValueError("BLOCKED: runtime needs bin/python and chromium/chrome")
    command = [
        shutil.which("bwrap") or "bwrap",
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--clearenv",
        "--setenv",
        "PATH",
        "/runtime/bin:/usr/bin",
        "--setenv",
        "HOME",
        "/tmp",  # noqa: S108 -- private namespace tmpfs
        "--setenv",
        "PYTHONNOUSERSITE",
        "1",
        "--setenv",
        "LANG",
        "C.UTF-8",
        "--ro-bind",
        "/usr",
        "/usr",
    ]
    for directory in ["/lib", "/lib64"]:
        if Path(directory).exists():
            command += ["--ro-bind", directory, directory]
    command += ["--dir", "/etc"]
    for directory in ["/etc/fonts", "/etc/ld.so.cache"]:
        if Path(directory).exists():
            command += ["--ro-bind", directory, directory]
    command += [
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",  # noqa: S108 -- new private tmpfs
        "--ro-bind",
        str(runtime),
        "/runtime",
        "--ro-bind",
        str(ROOT / "scripts/browser_worker.py"),
        "/worker.py",
        "--ro-bind",
        str(work / "input.html"),
        "/input.html",
        "--bind",
        str(work / "output"),
        "/output",
        "--chdir",
        "/tmp",  # noqa: S108 -- namespace-local cwd
        "/runtime/bin/python",
        "-I",
        "/worker.py",
    ]
    return command


def run_export(args: argparse.Namespace) -> None:
    if not math.isfinite(args.scale) or not 1 <= args.scale <= 4:
        raise ValueError("scale must be finite and between 1 and 4")
    source_path = project_path(args.source, existing=True)
    output_path = project_path(args.output, existing=False)
    if source_path.suffix.lower() != ".html" or output_path.suffix not in {".svg", ".png"}:
        raise ValueError("expected HTML input and SVG or PNG output")
    if output_path.suffix == ".png" and not args.approve_browser_export:
        raise ValueError("DENIED: explicit current-session approval required for browser export")
    source = read_bounded(source_path)
    validate(source, args.scale)
    audit(
        "preflight",
        source_sha256=sha256(source),
        format=output_path.suffix[1:],
        scale=args.scale,
        browser_approval_acknowledged=args.approve_browser_export,
    )
    with tempfile.TemporaryDirectory(prefix="diagram-export-") as temporary:
        work = Path(temporary)
        snapshot = work / "input.html"
        snapshot.write_bytes(source)
        checked = subprocess.run(  # noqa: S603 -- fixed local validator, data path in argv
            [sys.executable, str(ROOT / "scripts/self_check.py"), "--offline", str(snapshot)],
            capture_output=True,
            text=True,
            timeout=15,
            preexec_fn=process_limits,
        )
        if checked.returncode:
            audit(
                "quality_check_failed",
                diagnostic_sha256=sha256(checked.stdout.encode()),
                diagnostic="offline document-quality check failed; output withheld",
            )
            raise ValueError("offline quality check failed; inspect the approved input locally")
        if output_path.suffix == ".svg":
            invocation = (
                "import runpy,sys; from pathlib import Path; "
                "m=runpy.run_path(sys.argv[1]); p=Path(sys.argv[2]); "
                "Path(sys.argv[3]).write_text(m['export_svg_document'](p.read_text(),p,system_fonts=True))"
            )
            result = subprocess.run(  # noqa: S603 -- fixed code string, paths passed as data argv
                [
                    sys.executable,
                    "-I",
                    "-c",
                    invocation,
                    str(ROOT / "scripts/upstream_export_svg.py"),
                    str(snapshot),
                    str(work / "output.svg"),
                ],
                capture_output=True,
                timeout=20,
                preexec_fn=process_limits,
            )
            if result.returncode:
                raise ValueError("SVG extraction failed")
            if result.stderr.strip():
                audit(
                    "export_warning",
                    diagnostic="SVG transformer reported a warning; output withheld",
                    diagnostic_sha256=sha256(result.stderr),
                )
                raise ValueError("SVG transformation warning requires review; no output saved")
            data = read_bounded(work / "output.svg", MAX_OUTPUT)
            validate(data, args.scale, svg_only=True)
        else:
            if not args.runtime:
                raise ValueError("BLOCKED: separately provisioned browser runtime required")
            if not BROWSER_EXPORT_VALIDATED:
                raise ValueError("BLOCKED: browser export release gate awaits live Chromium/isolation validation")
            (work / "output").mkdir()
            command = sandbox_command(Path(args.runtime), work)
            audit("browser_start", isolation="bubblewrap-unshare-all", capture="complete-static-frame")
            result = subprocess.run(  # noqa: S603 -- fixed isolation runner, no shell
                command + [str(args.scale)], capture_output=True, timeout=45, preexec_fn=process_limits
            )
            if result.returncode:
                raise ValueError("BLOCKED: isolated browser readiness/render checks failed")
            data = read_bounded(work / "output/diagram.png", MAX_OUTPUT)
            if not data.startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValueError("renderer returned invalid PNG")
    # Exclusive creation refuses overwrite; parent paths are rechecked after the
    # subprocess. Trusted project concurrency is assumed, not a filesystem sandbox.
    output_path = project_path(args.output, existing=False)
    with output_path.open("xb") as stream:
        stream.write(data)
    audit("export_saved", output_sha256=sha256(data), bytes=len(data), format=output_path.suffix[1:])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source")
    parser.add_argument("output")
    parser.add_argument("--scale", type=float, default=2)
    parser.add_argument("--approve-browser-export", action="store_true")
    parser.add_argument("--runtime")
    args = parser.parse_args()
    try:
        run_export(args)
        return 0
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        audit("export_failed", error=str(error))
        return 1


if __name__ == "__main__":
    sys.exit(main())
