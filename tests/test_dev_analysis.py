import importlib.util
import json


def test_dev_analysis_bootstrap_is_bounded_retry_safe_and_keeps_shared_cache(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "prepare_dev_analysis", "scripts/prepare_dev_analysis.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = tmp_path / "shared"
    source.mkdir()
    (source / "public_manifest.json").write_text("{}")
    target = tmp_path / "dev"
    calls = []

    def generate(**kwargs):
        calls.append(kwargs)
        (target / "analysis").mkdir(parents=True)
        return {
            "status": "ok",
            "source_clip_count": 2,
            "channels": {"14": 2},
            "topics": {"status": "ok"},
        }

    monkeypatch.setattr(module, "generate_lexical_analysis_from_public_manifest", generate)
    first = module.prepare(source, target)
    assert module.prepare(source, target) == first
    assert len(calls) == 1 and calls[0]["limit"] == 2500
    assert calls[0]["output_dir"] == target
    assert json.loads((source / "public_manifest.json").read_text()) == {}
