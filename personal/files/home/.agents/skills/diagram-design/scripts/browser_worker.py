#!/usr/bin/env python3
"""Internal isolated renderer. Never invoke outside export_diagram.py."""

from __future__ import annotations

import socket
import sys
from pathlib import Path


def assert_isolation() -> None:
    # Host loopback is absent in a fresh network namespace; no sensitive mounts
    # or external interface is allowed. These are readiness checks, not a substitute
    # for trusted Bubblewrap invocation and operator-provisioned browser binaries.
    interfaces = {
        line.split(":", 1)[0].strip() for line in Path("/proc/net/dev").read_text().splitlines() if ":" in line
    }
    if interfaces - {"lo"}:
        raise RuntimeError("external network interface visible")
    with socket.socket() as connection:
        connection.settimeout(1)
        try:
            connection.connect(("1.1.1.1", 443))
        except OSError:
            pass
        else:
            raise RuntimeError("network isolation failed")
    if Path("/home/agent").exists() or Path("/root/.ssh").exists():
        raise RuntimeError("sensitive host mount visible")


def main() -> int:
    assert_isolation()
    from playwright.sync_api import sync_playwright

    scale = float(sys.argv[1])
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path="/runtime/chromium/chrome",
            chromium_sandbox=True,
            args=["--disable-dev-shm-usage", "--disable-background-networking"],
        )
        try:
            context = browser.new_context(device_scale_factor=scale, service_workers="block", accept_downloads=False)
            blocked: list[str] = []

            def route(request):
                if request.request.url.split("?", 1)[0] == "file:///input.html":
                    request.continue_()
                else:
                    blocked.append("resource request")
                    request.abort()

            context.route("**/*", route)
            page = context.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto("file:///input.html?motion=static", wait_until="load", timeout=15_000)
            page.evaluate("document.fonts.ready")
            if errors or blocked:
                raise RuntimeError("unexpected browser error/resource request")
            if not page.locator("[data-motion-root]").evaluate_all(
                "roots => roots.every(root => root.dataset.frame === 'static')"
            ):
                raise RuntimeError("complete static motion frame not reached")
            svg = page.locator("svg")
            if svg.count() != 1:
                raise RuntimeError("one SVG required")
            svg.evaluate("""el => {
                const b = el.viewBox.baseVal;
                if (![b.width,b.height].every(n => Number.isFinite(n) && n>0)
                    || Math.max(b.width,b.height)>8192 || b.width*b.height>16000000)
                    throw Error('dimensions exceed conservative renderer budget');
                for (const [axis,size] of [['width',b.width],['height',b.height]])
                    for (const prefix of ['', 'min-', 'max-'])
                        el.style.setProperty(prefix+axis,size+'px','important');
                for (let a=el.parentElement;a;a=a.parentElement)
                    a.style.setProperty('overflow','visible','important');
            }""")
            svg.screenshot(path="/output/diagram.png", omit_background=True, timeout=15_000)
            if errors or blocked:
                raise RuntimeError("unexpected browser error/resource request")
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"isolated renderer failed: {type(error).__name__}", file=sys.stderr)
        sys.exit(1)
