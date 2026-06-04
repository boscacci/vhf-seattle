from __future__ import annotations

from pathlib import Path

from talkingboats.hls_publisher import HlsPublisher, render_hls_public_paths


class FakeS3:
    def __init__(self) -> None:
        self.puts: list[dict[str, object]] = []
        self.deletes: list[dict[str, object]] = []

    def put_object(self, **kwargs) -> None:
        self.puts.append(kwargs)

    def delete_object(self, **kwargs) -> None:
        self.deletes.append(kwargs)


def test_render_hls_public_paths_uses_same_origin_cloud_paths() -> None:
    paths = render_hls_public_paths(["14", "68"])

    assert paths["default"] == "/live/current.m3u8"
    assert paths["channels"]["14"] == "/live/channels/14/current.m3u8"
    assert paths["channels"]["68"] == "/live/channels/68/current.m3u8"


def test_hls_publisher_uploads_playlists_without_cache_and_segments_with_short_cache(
    tmp_path: Path,
) -> None:
    root = tmp_path / "hls"
    channel_dir = root / "channels" / "68"
    segment_dir = channel_dir / "segments"
    segment_dir.mkdir(parents=True)
    playlist = channel_dir / "current.m3u8"
    segment = segment_dir / "seg-00001.ts"
    channels_json = root / "channels.json"
    playlist.write_text("#EXTM3U\nsegments/seg-00001.ts\n", encoding="utf-8")
    segment.write_bytes(b"segment")
    channels_json.write_text('{"channels":[]}\n', encoding="utf-8")
    s3 = FakeS3()

    publisher = HlsPublisher(
        root_dir=root,
        bucket="public-bucket",
        prefix="live",
        s3_client=s3,
    )
    uploaded = publisher.publish_once()

    assert uploaded == 3
    puts_by_key = {put["Key"]: put for put in s3.puts}
    assert puts_by_key["live/channels.json"]["ContentType"] == "application/json"
    assert puts_by_key["live/channels.json"]["CacheControl"] == "no-store"
    assert puts_by_key["live/channels/68/current.m3u8"]["ContentType"] == (
        "application/vnd.apple.mpegurl"
    )
    assert puts_by_key["live/channels/68/current.m3u8"]["CacheControl"] == "no-store"
    assert puts_by_key["live/channels/68/segments/seg-00001.ts"]["ContentType"] == "video/mp2t"
    assert puts_by_key["live/channels/68/segments/seg-00001.ts"]["CacheControl"] == (
        "max-age=10"
    )


def test_hls_publisher_deletes_removed_segments_but_not_missing_playlists(tmp_path: Path) -> None:
    root = tmp_path / "hls"
    segment_dir = root / "channels" / "68" / "segments"
    segment_dir.mkdir(parents=True)
    segment = segment_dir / "seg-00001.ts"
    segment.write_bytes(b"segment")
    s3 = FakeS3()
    publisher = HlsPublisher(root_dir=root, bucket="public-bucket", prefix="live", s3_client=s3)

    publisher.publish_once()
    segment.unlink()
    publisher.publish_once()

    assert s3.deletes == [
        {"Bucket": "public-bucket", "Key": "live/channels/68/segments/seg-00001.ts"}
    ]
