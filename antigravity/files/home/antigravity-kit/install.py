#!/usr/bin/env python3
"""Install a checksum-pinned official Antigravity binary, without shell setup."""

import argparse
import hashlib
import os
import platform
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path

VERSION = "1.4.12"
BUILD = "4768735748292608"
PINS = {
    "aarch64": (
        "linux-arm/cli_linux_arm64.tar.gz",
        "7cae317fb6a02eb387982f06bfb234b366879cf9a80ad8969b571e5a55d1e37a6a5a49cd6b703c0443bb417937cf5e3b14a8c80cb26917ad79eef723a9f374c7",
    ),
    "x86_64": (
        "linux-x64/cli_linux_x64.tar.gz",
        "ea01c73b772187bca928852cf96235f0d846d6da5ebdac188b9ae719597465737f325540d483ee5f3f62d151029001713344972a187ddfb98cc7b97f7204b7f4",
    ),
}


def extract(archive, digest, destination):
    with archive.open("rb") as source:
        if hashlib.file_digest(source, "sha512").hexdigest() != digest:
            raise ValueError("Antigravity archive checksum mismatch")
    with tarfile.open(archive, "r:gz") as bundle:
        members = [m for m in bundle.getmembers() if m.name == "antigravity"]
        if len(members) != 1 or not members[0].isreg() or not 1 <= members[0].size <= 500_000_000:
            raise ValueError("archive must contain one bounded regular CLI binary")
        with bundle.extractfile(members[0]) as source, destination.open("xb") as target:
            shutil.copyfileobj(source, target)
    destination.chmod(0o755)


def install():
    if os.geteuid() == 0 or platform.system() != "Linux" or platform.machine() not in PINS:
        raise ValueError("install as the agent on Linux ARM64 or x64")
    platform_path, digest = PINS[platform.machine()]
    prefix = Path.home() / ".local/share/acq/antigravity"
    prefix.mkdir(parents=True, exist_ok=True)
    marker = prefix / "installed"
    if marker.is_file() and marker.read_text() == VERSION + ":" + digest and (prefix / "agy").is_file():
        return
    url = f"https://storage.googleapis.com/antigravity-public/antigravity-cli/{VERSION}-{BUILD}/{platform_path}"
    with tempfile.TemporaryDirectory(prefix="install-", dir=prefix) as directory:
        stage = Path(directory)

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args):
                raise ValueError("unexpected Antigravity download redirect")

        with (
            urllib.request.build_opener(NoRedirect).open(url, timeout=120) as response,
            (stage / "cli.tgz").open("xb") as target,
        ):  # noqa: S310 -- fixed official URL, redirects denied
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > 500_000_000:
                    raise ValueError("CLI archive exceeds size limit")
                target.write(chunk)
        extract(stage / "cli.tgz", digest, stage / "agy")
        os.replace(stage / "agy", prefix / "agy")
        marker.write_text(VERSION + ":" + digest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    if parser.parse_args().apply:
        install()
    else:
        print(f"Would install Antigravity {VERSION} in the agent home")
