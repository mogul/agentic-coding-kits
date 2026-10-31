#!/usr/bin/env python3
"""Install the pinned CLI and wheel-only, hash-locked bridge as the agent user."""

import argparse
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

VERSION = "2.1.314"
PINS = {
    "x86_64": ("x64", "c6b690e52ba2d038c4c8d2566b2ec35acef4995c4321f7d57fa464a7088c2b78"),
    "aarch64": ("arm64", "5a8087f6b0df5796326bb8e58c6e89637c58f28a16aea45434a7e914e854b0dc"),
}
PIP_URL = (
    "https://files.pythonhosted.org/packages/3f/06/"
    "3e4420302363fbb71be3c7f35ce042f54bfca330e3e66b3a2e3c4cca579f/pip-26.2.2-py3-none-any.whl"
)
PIP_SHA256 = "fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70"


def bootstrap_venv(prefix, stage):
    # Debian/Ubuntu split ensurepip into a separate package. stdlib venv without
    # seeding works without it; a verified universal wheel supplies pip instead.
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(prefix / "venv")], check=True)  # noqa: S603 -- fixed interpreter/module argv
    wheel = stage / "pip-26.2.2-py3-none-any.whl"
    with urllib.request.urlopen(PIP_URL, timeout=120) as response, wheel.open("xb") as target:  # noqa: S310 -- fixed HTTPS URL
        if response.geturl() != PIP_URL:
            raise ValueError("unexpected pip download redirect")
        shutil.copyfileobj(response, target)
    with wheel.open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != PIP_SHA256:
            raise ValueError("pip wheel SHA-256 mismatch")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(wheel)
    subprocess.run(  # noqa: S603 -- verified wheel and fixed pip argv, no shell
        [
            str(prefix / "venv/bin/python"),
            "-m",
            "pip",
            "install",
            "--isolated",
            "--no-index",
            "--no-deps",
            "--force-reinstall",
            str(wheel),
        ],
        env=env,
        check=True,
    )  # noqa: S603 -- verified wheel, fixed pip argv


def extract_binary(archive, digest, destination):
    with archive.open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != digest:
            raise ValueError("Claude archive SHA-256 mismatch")
    with tarfile.open(archive, "r:gz") as bundle:
        members = [m for m in bundle.getmembers() if m.name == "package/claude"]
        if len(members) != 1 or not members[0].isreg():
            raise ValueError("archive must contain one regular package/claude")
        if not 1 <= members[0].size <= 500_000_000:
            raise ValueError("invalid binary size")
        with bundle.extractfile(members[0]) as source, destination.open("xb") as target:
            shutil.copyfileobj(source, target)
    destination.chmod(0o755)


def install():
    if os.geteuid() == 0:
        raise ValueError("install must run as the unprivileged agent")
    if platform.system() != "Linux" or platform.machine() not in PINS:
        raise ValueError("supported guests: glibc Linux x86_64 and aarch64")
    if not (3, 12) <= tuple(sys.version_info[:2]) < (3, 15):
        raise ValueError("bridge requires Python 3.12–3.14 with stdlib venv")
    prefix = Path.home() / ".local/share/acq/claude-code"
    prefix.mkdir(parents=True, exist_ok=True)
    lock = Path(__file__).with_name("requirements.lock")
    stamp = VERSION + ":" + PIP_SHA256 + ":" + hashlib.sha256(lock.read_bytes()).hexdigest()
    marker = prefix / "installed"
    if (
        marker.is_file()
        and marker.read_text() == stamp
        and (prefix / "claude").is_file()
        and (prefix / "venv/bin/python").is_file()
    ):
        return
    arch, digest = PINS[platform.machine()]
    url = f"https://registry.npmjs.org/@anthropic-ai/claude-code-linux-{arch}/-/claude-code-linux-{arch}-{VERSION}.tgz"
    with tempfile.TemporaryDirectory(prefix="install-", dir=prefix) as temporary:
        stage = Path(temporary)
        archive = stage / "claude.tgz"
        # URL is constructed exclusively from the fixed HTTPS registry and architecture pins.
        with urllib.request.urlopen(url, timeout=120) as response, archive.open("xb") as target:  # noqa: S310
            if response.geturl() != url:
                raise ValueError("unexpected download redirect")
            shutil.copyfileobj(response, target)
        extract_binary(archive, digest, stage / "claude")
        # Fixed interpreter/module invocations, argv form; no external command strings.
        bootstrap_venv(prefix, stage)
        subprocess.run(  # noqa: S603 -- fixed interpreter and pip argv, hash-locked input
            [
                str(prefix / "venv/bin/python"),
                "-m",
                "pip",
                "install",  # noqa: S603
                "--isolated",
                "--require-hashes",
                "--only-binary=:all:",
                "--index-url",
                "https://pypi.org/simple",
                "--timeout",
                "60",
                "--retries",
                "0",
                "-r",
                str(lock),
            ],
            check=True,
        )
        os.replace(stage / "claude", prefix / "claude")
        marker.write_text(stamp)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="install; otherwise preview only")
    args = parser.parse_args()
    if args.apply:
        install()
    else:
        print(f"Would install Claude Code {VERSION} and the locked LiteLLM bridge in the agent home")
