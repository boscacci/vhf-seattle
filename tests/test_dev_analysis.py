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


def test_approved_cache_promotion_preserves_search_and_prefers_full_safe_analysis(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "prepare_dev_analysis", "scripts/prepare_dev_analysis.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    snapshot, site = tmp_path / "snapshot", tmp_path / "site"
    for root in [snapshot, site]:
        (root / "analysis").mkdir(parents=True)
    (snapshot / "analysis/lexical.json").write_text(
        json.dumps(
            {
                "status": "ok",
                "source_clip_count": 2,
                "channels": {"14": 2},
            }
        )
    )
    (snapshot / "analysis/topic_clusters.html").write_text("safe model plot")
    (site / "analysis/search_index.json").write_text("preserved search")
    module.promote_if_missing(snapshot, site)
    assert (site / "analysis/topic_clusters.html").read_text() == "safe model plot"
    assert (site / "analysis/search_index.json").read_text() == "preserved search"
    (site / "analysis/lexical.json").write_text(
        json.dumps(
            {
                "status": "ok",
                "source_clip_count": 50,
                "channels": {"14": 50},
            }
        )
    )
    module.promote_if_missing(snapshot, site)
    assert json.loads((site / "analysis/lexical.json").read_text())["source_clip_count"] == 50
