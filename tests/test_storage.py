from datetime import UTC, datetime

from talkingboats.config import LiveChannel, Settings
from talkingboats.schemas import ClipPresignRequest
from talkingboats.storage import S3AudioStorage, is_allowed_audio_key, raw_clip_key


def test_raw_clip_key_is_stable_and_does_not_include_receiver_details() -> None:
    request = ClipPresignRequest(
        channel="68",
        started_at=datetime(2026, 5, 20, 19, 12, tzinfo=UTC),
        content_type="audio/mpeg",
        idempotency_key="receiver-serial-and-local-path-should-be-hashed",
    )

    key = raw_clip_key(request)

    assert key.startswith("raw/channel=68/date=2026-05-20/20260520T191200Z-")
    assert key.endswith(".mp3")
    assert "receiver-serial" not in key
    assert "local-path" not in key


def test_playback_key_validation_allows_only_audio_prefixes() -> None:
    assert is_allowed_audio_key("raw/channel=14/date=2026-05-20/file.mp3")
    assert is_allowed_audio_key("raw/channel=66A/date=2026-05-20/file.wav")
    assert is_allowed_audio_key("hall-of-fame/channel=68/file.ogg")

    assert not is_allowed_audio_key("../raw/channel=14/file.mp3")
    assert not is_allowed_audio_key("/raw/channel=14/file.mp3")
    assert not is_allowed_audio_key("public/channel=14/file.mp3")
    assert not is_allowed_audio_key("raw//channel=14/file.mp3")


def test_raw_upload_presign_marks_clip_as_not_featured_by_default() -> None:
    client = CapturingS3Client()
    storage = S3AudioStorage(_settings(), client=client)
    request = ClipPresignRequest(
        channel="68",
        started_at=datetime(2026, 5, 20, 19, 12, tzinfo=UTC),
        content_type="audio/mpeg",
        idempotency_key="receiver-serial-and-local-path-should-be-hashed",
    )

    key, upload_url = storage.presign_raw_upload(request)

    assert upload_url == "https://s3.example.test/upload"
    assert key.startswith("raw/channel=68/date=2026-05-20/")
    assert client.presigned_params["Tagging"] == "talkingboats-featured=false"


def test_storage_updates_raw_clip_featured_tag() -> None:
    client = CapturingS3Client()
    storage = S3AudioStorage(_settings(), client=client)

    storage.tag_raw_clip_featured("raw/channel=14/date=2026-05-20/file.mp3", featured=True)
    storage.tag_raw_clip_featured("raw/channel=14/date=2026-05-20/file.mp3", featured=False)

    assert client.tagging_calls == [
        {
            "Bucket": "raw-bucket",
            "Key": "raw/channel=14/date=2026-05-20/file.mp3",
            "Tagging": {"TagSet": [{"Key": "talkingboats-featured", "Value": "true"}]},
        },
        {
            "Bucket": "raw-bucket",
            "Key": "raw/channel=14/date=2026-05-20/file.mp3",
            "Tagging": {"TagSet": [{"Key": "talkingboats-featured", "Value": "false"}]},
        },
    ]


def test_storage_lists_only_allowed_raw_audio_keys() -> None:
    client = CapturingS3Client(
        pages=[
            {
                "Contents": [
                    {"Key": "raw/channel=14/date=2026-05-20/file.mp3"},
                    {"Key": "../raw/channel=14/date=2026-05-20/file.mp3"},
                    {"Key": "public/file.mp3"},
                ]
            }
        ]
    )
    storage = S3AudioStorage(_settings(), client=client)

    assert list(storage.iter_raw_audio_keys()) == ["raw/channel=14/date=2026-05-20/file.mp3"]
    assert client.paginate_calls == [{"Bucket": "raw-bucket", "Prefix": "raw/"}]


def test_playback_exists_caches_positive_results_across_storage_instances() -> None:
    S3AudioStorage._playback_exists_cache.clear()
    client = CapturingS3Client()
    key = "raw/channel=14/date=2026-05-20/file.mp3"
    storage = S3AudioStorage(_settings(), client=client)
    other_storage = S3AudioStorage(_settings(), client=client)

    assert storage.playback_exists(key) is True
    assert other_storage.playback_exists(key) is True

    assert client.head_calls == [{"Bucket": "raw-bucket", "Key": key}]


class CapturingS3Client:
    def __init__(self, pages=None) -> None:
        self.presigned_params = {}
        self.tagging_calls = []
        self.pages = pages or []
        self.paginate_calls = []
        self.head_calls = []

    def generate_presigned_url(self, operation, *, Params, ExpiresIn):
        assert operation == "put_object"
        assert ExpiresIn == 900
        self.presigned_params = Params
        return "https://s3.example.test/upload"

    def put_object_tagging(self, **kwargs):
        self.tagging_calls.append(kwargs)

    def head_object(self, **kwargs):
        self.head_calls.append(kwargs)

    def get_paginator(self, operation):
        assert operation == "list_objects_v2"
        return self

    def paginate(self, **kwargs):
        self.paginate_calls.append(kwargs)
        return self.pages


def _settings() -> Settings:
    return Settings(
        aws_region="us-west-2",
        raw_bucket="raw-bucket",
        public_bucket="public-bucket",
        ingest_token="ingest-token",
        raw_presign_seconds=900,
        playback_presign_seconds=300,
        public_site_dir="outputs/public-site",
        public_base_url="https://seattleboatradio.com",
        live_channels={
            "68": LiveChannel(
                channel="68",
                label="Recreational",
                frequency_mhz=156.425,
                stream_url=None,
            )
        },
    )
