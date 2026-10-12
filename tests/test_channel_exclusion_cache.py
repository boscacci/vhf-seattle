import json

from talkingboats.channel_exclusion_cache import sanitize_caches


def test_stale_74_caches_are_removed_without_touching_raw_history(tmp_path):
    site = tmp_path / "public"
    (site / "analysis").mkdir(parents=True)
    raw = tmp_path / "raw-history.mp3"
    raw.write_bytes(b"preserved original")
    manifest = {
        "generated_at": "2026-10-12T12:00:00Z",
        "site": {},
        "stats": {},
        "clips": [
            {
                "channel": channel,
                "id": channel,
                "public_title": "radio test",
                "started_at": "2026-10-05T12:00:00Z",
                "transcript_public": "radio test",
                "audio_url": "/clips/fixture.mp3",
            }
            for channel in ["14", "74", "68"]
        ],
    }
    (site / "public_manifest.json").write_text(json.dumps(manifest))
    (site / "analysis/lexical.json").write_text(json.dumps({"status": "ok", "channels": {"74": 1}}))
    (site / "analysis/topic_clusters.html").write_text("<p>channel=74</p>")
    (site / "analysis/search_index.json").write_text(json.dumps({"clips": manifest["clips"]}))
    backup = tmp_path / "private-backup"
    sanitize_caches(site, backup)
    assert raw.read_bytes() == b"preserved original"
    assert [
        r["channel"] for r in json.loads((site / "public_manifest.json").read_text())["clips"]
    ] == ["14", "68"]
    assert json.loads((site / "analysis/lexical.json").read_text())["status"] == "missing"
    assert [
        r["channel"] for r in json.loads((site / "analysis/search_index.json").read_text())["clips"]
    ] == ["14", "68"]
    assert json.loads((backup / "public_manifest.json").read_text()) == manifest
    assert "channel=74" not in (site / "analysis/topic_clusters.html").read_text()
