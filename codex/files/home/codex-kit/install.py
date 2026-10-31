#!/usr/bin/env python3
"""Install a checksum-pinned official Codex archive without package scripts."""

import argparse
import hashlib
import os
import platform
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

VERSION = "0.166.0"
MAX_ARCHIVE = 500_000_000
PINS = {
    "aarch64": ("aarch64", "94eb707605ec2646b2e05b7edf7c4e7b3ccf02b16237c34ae9beb8cfb7f810a9"),
    "x86_64": ("x86_64", "a0bf572d2f93f056c6712a6da348e96078dc84f3885fd7be67807ef389cb3978"),
}


def extract(archive, digest, member_name, destination, algorithm="sha256"):
    with archive.open("rb") as source:
        if hashlib.file_digest(source, algorithm).hexdigest() != digest:
            raise ValueError("CLI archive checksum mismatch")
    with tarfile.open(archive, "r:gz") as bundle:
        members = [m for m in bundle.getmembers() if m.name == member_name]
        if len(members) != 1 or not members[0].isreg() or not 1 <= members[0].size <= 500_000_000:
            raise ValueError("archive must contain one bounded regular CLI binary")
        with bundle.extractfile(members[0]) as source, destination.open("xb") as target:
            shutil.copyfileobj(source, target)
    destination.chmod(0o755)


def install():
    if os.geteuid() == 0 or platform.system() != "Linux" or platform.machine() not in PINS:
        raise ValueError("install as the agent on Linux ARM64 or x64")
    arch, digest = PINS[platform.machine()]
    prefix = Path.home() / ".local/share/acq/codex"
    prefix.mkdir(parents=True, exist_ok=True)
    marker = prefix / "installed"
    if marker.is_file() and marker.read_text() == VERSION + ":" + digest and (prefix / "codex").is_file():
        return
    url = f"https://github.com/openai/codex/releases/download/rust-v{VERSION}/codex-{arch}-unknown-linux-musl.tar.gz"
    with tempfile.TemporaryDirectory(prefix="install-", dir=prefix) as directory:
        stage = Path(directory)

        # GitHub release redirects are expected; allow only its HTTPS asset host.
        class Redirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, request, fp, code, msg, headers, newurl):
                resolved = urlsplit(newurl)
                if resolved.scheme != "https" or resolved.hostname not in (
                    "github.com",
                    "release-assets.githubusercontent.com",
                ):
                    raise ValueError("unexpected CLI download redirect")
                return super().redirect_request(request, fp, code, msg, headers, newurl)

        with (
            urllib.request.build_opener(Redirect).open(url, timeout=120) as response,
            (stage / "cli.tgz").open("xb") as target,
        ):  # noqa: S310 -- fixed official URL with pre-follow redirect validation
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_ARCHIVE:
                    raise ValueError("CLI archive exceeds size limit")
                target.write(chunk)
        extract(stage / "cli.tgz", digest, f"codex-{arch}-unknown-linux-musl", stage / "codex")
        os.replace(stage / "codex", prefix / "codex")
        marker.write_text(VERSION + ":" + digest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    if parser.parse_args().apply:
        install()
    else:
        print(f"Would install Codex {VERSION} in the agent home")
