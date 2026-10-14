import hashlib
import importlib.util
import io
import tarfile

import pytest

spec = importlib.util.spec_from_file_location(
    "docktalk_builder", "scripts/build_docktalk_artifact.py"
)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def test_installer_checksum_mismatch_fails_before_execution(tmp_path, monkeypatch):
    class Response(io.BytesIO):
        pass

    monkeypatch.setattr(builder.urllib.request, "urlopen", lambda *a, **kw: Response(b"changed"))
    policy = {
        "mode": "alongside",
        "installer_url": "https://docktalk-edge.fly.dev/install",
        "installer_sha256": "a" * 64,
    }
    with pytest.raises(ValueError):
        builder.verified_installer(policy, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_artifact_bundles_reviewed_installer_deterministically(tmp_path):
    tree = io.BytesIO()
    with tarfile.open(fileobj=tree, mode="w") as archive:
        entry = tarfile.TarInfo("source.txt")
        entry.size = 3
        archive.addfile(entry, io.BytesIO(b"git"))
    a, b = tmp_path / "a.tar.gz", tmp_path / "b.tar.gz"
    builder.write_artifact(tree.getvalue(), b"reviewed", a)
    builder.write_artifact(tree.getvalue(), b"reviewed", b)
    assert hashlib.sha256(a.read_bytes()).digest() == hashlib.sha256(b.read_bytes()).digest()
    with tarfile.open(a) as archive:
        assert archive.extractfile("vendor/docktalk-installer.sh").read() == b"reviewed"
        assert archive.extractfile("source.txt").read() == b"git"
