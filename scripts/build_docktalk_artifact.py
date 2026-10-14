"""Bundle the exact Git tree and reviewed upstream installer; never execute downloaded code."""

import gzip
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path


def verified_installer(spec, cache):
    if (
        spec["mode"] != "alongside"
        or spec["installer_url"] != "https://docktalk-edge.fly.dev/install"
    ):
        raise ValueError("only reviewed alongside installer is permitted")
    expected = spec["installer_sha256"]
    if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise ValueError("invalid installer identity")
    cache.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = cache / (expected + ".sh")
    if path.exists():
        payload = path.read_bytes()
    else:
        with urllib.request.urlopen(spec["installer_url"], timeout=20) as response:
            payload = response.read(262145)
    if len(payload) > 262144 or hashlib.sha256(payload).hexdigest() != expected:
        raise ValueError("upstream installer differs from reviewed identity")
    if not path.exists():
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
    return payload


def write_artifact(tree, installer, destination):
    with (
        destination.open("xb") as target,
        gzip.GzipFile(fileobj=target, mode="wb", filename="", mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w|") as archive,
    ):
        with tarfile.open(fileobj=io.BytesIO(tree)) as source:
            for item in source:
                archive.addfile(item, source.extractfile(item) if item.isfile() else None)
        item = tarfile.TarInfo("vendor/docktalk-installer.sh")
        item.size, item.mode, item.mtime = len(installer), 0o644, 0
        archive.addfile(item, io.BytesIO(installer))


if __name__ == "__main__":
    repo, commit, destination = sys.argv[1:]
    spec = json.loads(
        subprocess.check_output(["git", "-C", repo, "show", commit + ":config/docktalk.json"])
    )
    payload = verified_installer(spec, Path.home() / ".cache/talkingboats/reviewed-installers")
    tree = subprocess.check_output(["git", "-C", repo, "archive", "--format=tar", commit])
    write_artifact(tree, payload, Path(destination))
